# main.py ーー 完全置き換え版
import os
import time
import json
import threading
import traceback
from collections import deque, OrderedDict
import re
from pathlib import Path

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError
from openai import OpenAI

# =========================
# 基本設定
# =========================
app = Flask(__name__)
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# 設定ファイルのロード（ホットリロード対応）
# =========================
BASE = Path(__file__).parent
_PROFILE_PATH   = BASE / "asaoka_profile.json"
_PLAYBOOK_PATH  = BASE / "asaoka_playbooks.json"
_REDFLAGS_PATH  = BASE / "asaoka_redflags.json"
_PHRASEBANK_PATH= BASE / "asaoka_phrasebank.json"

_profile_cache  = {"data": None, "mtime": 0}
_playbook_cache = {"data": None, "mtime": 0}
_redflags_cache = {"data": None, "mtime": 0}
_phrase_cache   = {"data": None, "mtime": 0}

def _load_json(path: Path, cache: dict):
    try:
        st = path.stat()
        if st.st_mtime != cache["mtime"]:
            with path.open("r", encoding="utf-8") as f:
                cache["data"] = json.load(f)
            cache["mtime"] = st.st_mtime
            app.logger.info(f"Loaded {path.name}")
    except FileNotFoundError:
        cache["data"] = {}
        app.logger.warning(f"{path.name} not found. Using empty.")
    except Exception as e:
        app.logger.error(f"Load error {path.name}: {e}\n{traceback.format_exc()}")

def load_profile(force=False):
    try:
        if force:
            _profile_cache["mtime"] = 0
        _load_json(_PROFILE_PATH, _profile_cache)
        ver = _profile_cache["data"].get("profile_version", "unknown")
        app.logger.info(f"Profile loaded: version={ver}")
    except Exception as e:
        app.logger.error(f"Profile load error: {e}\n{traceback.format_exc()}")
        _profile_cache["data"] = {
            "name":"AsaokaAI",
            "question_policy":{"max_questions":2, "risk_based_skip_if_confidence_over":0.8},
            "tone_rules":{"style":"敬体・簡潔・論理","avoid_endings":["だ","なのです","のです"],"quote_rules":{"emphasis":"『』","speech":"「」"}},
            "taboo_map":{}
        }

def get_profile():
    _load_json(_PROFILE_PATH, _profile_cache);   return _profile_cache["data"] or {}
def get_playbooks():
    _load_json(_PLAYBOOK_PATH, _playbook_cache); return _playbook_cache["data"] or {}
def get_redflags():
    _load_json(_REDFLAGS_PATH, _redflags_cache); return _redflags_cache["data"] or {}
def get_phrasebank():
    _load_json(_PHRASEBANK_PATH, _phrase_cache); return _phrase_cache["data"] or {}

# 起動時に一度読む
load_profile(force=True)
get_playbooks(); get_redflags(); get_phrasebank()

# =========================
# 応答時間の自己調整（待機閾値）
# =========================
metrics = {"samples": deque(maxlen=200), "ema": None, "n": 0}
def record_elapsed(sec: float):
    metrics["samples"].append(sec); metrics["n"] += 1
    alpha = 0.2
    metrics["ema"] = sec if metrics["ema"] is None else (1-alpha)*metrics["ema"] + alpha*sec
    app.logger.info(f"openai_elapsed={sec:.2f}s ema={metrics['ema']:.2f}s n={metrics['n']}")

def current_timeout() -> float:
    if metrics["n"] < 30 or metrics["ema"] is None: return 10.0
    t = metrics["ema"] * 1.3
    return max(8.0, min(18.0, t))

# =========================
# セッション & 重複返信の抑止
# =========================
sessions = {}  # key: push先ID -> dict

DEDUP_TTL       = 900   # 15分: 完了イベントの再処理を抑止
INFLIGHT_GRACE  = 120   # 2分 : 処理中イベントの重複を無視
PUSH_TTL        = 300   # 5分 : 同一本文の連投を抑止

processed_events = OrderedDict()  # key -> {"state":"inflight|done","ts":float}
recent_pushes    = OrderedDict()  # key -> ts

def _purge_odict(od, ttl):
    now = time.time()
    for k in list(od.keys()):
        ts = od[k]["ts"] if isinstance(od[k], dict) else od[k]
        if now - ts > ttl:
            od.pop(k, None)

def _event_key(event) -> str:
    mid = getattr(getattr(event, "message", None), "id", None)
    st  = event.source.type
    sid = getattr(event.source, "user_id", None) or getattr(event.source, "group_id", None) or getattr(event.source, "room_id", None)
    ts  = getattr(event, "timestamp", None)
    return f"{mid or event.reply_token}:{st}:{sid}:{ts}"

def _should_push(push_to: str, text: str) -> bool:
    _purge_odict(recent_pushes, PUSH_TTL)
    key = f"{push_to}:{hash(text)}"
    if key in recent_pushes:
        app.logger.info("dedup: skip duplicate push")
        return False
    recent_pushes[key] = time.time()
    return True

# =========================
# ユーティリティ
# =========================
def get_push_target(event):
    t = event.source.type
    if t == "user":  return event.source.user_id
    if t == "group": return event.source.group_id
    if t == "room":  return event.source.room_id
    return None

def get_session(push_to: str) -> dict:
    if push_to not in sessions:
        sessions[push_to] = {"stage":"S0","history":[],"used_surprise":False,"flags":{}}
    return sessions[push_to]

def sanitize(text: str) -> str:
    p = get_profile()
    taboo = p.get("taboo_map", {}) or {}
    out = text
    for k, v in taboo.items():
        out = out.replace(k, v)
    out = out.replace("なのです","です").replace("のです","です")
    return out

def classify_domain(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["彼氏","彼女","恋人","浮気","デート","既読","未読"]): return "love"
    if any(k in t for k in ["上司","部下","会社","職場","会議","納期","評価","人事"]): return "work"
    if any(k in t for k in ["家族","親","子","夫","妻","義理","兄弟","姉妹"]): return "family"
    return "general"

def scan_redflags(text: str) -> dict:
    rf = get_redflags() or {}
    hit = {"crisis": False, "derailers": [], "stalemate": False}
    crisis = rf.get("crisis", {}).get("keywords", [])
    if any(w in text for w in crisis): hit["crisis"] = True
    for w in (rf.get("derailers", {}).get("generalization", []) + rf.get("derailers", {}).get("personal_attack", [])):
        if w in text: hit["derailers"].append(w)
    if any(w in text for w in rf.get("stalemate", {}).get("phrases", [])): hit["stalemate"] = True
    return hit

def playbook_hint(domain: str, stage: str) -> str:
    pb = get_playbooks().get("domains", {}).get(domain, {})
    if not pb: return ""
    if stage == "S2":
        outline = " / ".join(pb.get("s2_outline", [])[:3])
        return f"[S2指針:{outline}]"
    if stage == "S3":
        opts = [o.get("label","") for o in pb.get("s3_options", [])][:3]
        return f"[S3候補:{' | '.join(opts)}]"
    return ""

# =========================
# プロンプト組み立て
# =========================
def build_system_prompt(sess: dict) -> str:
    p = get_profile()
    pr = p.get("priorities", {})
    priorities_line = "判断軸: " + " / ".join([
        f"真実性:{pr.get('truth',0):.2f}",
        f"関係維持:{pr.get('relationship',0):.2f}",
        f"時間効率:{pr.get('time_efficiency',0):.2f}",
        f"再発防止:{pr.get('recurrence_prevention',0):.2f}"
    ])
    doctrines = p.get("doctrines", {})
    env = p.get("environment_design", {})
    ideals = p.get("ideals_vs_reality", {})
    expol = p.get("expectation_policy", {})
    tone = p.get("tone_rules", {})
    qpol = p.get("question_policy", {"max_questions":2})
    quotes = tone.get("quote_rules", {"emphasis":"『』","speech":"「」"})

    core = f"""
あなたは「{p.get('name','AsaokaAI')}」です。出力は常に自然な敬体で、簡潔・論理的・実務的に回答します。
- 一般論で濁さず、前提の違いを明確化してから結論を提示します。
- 質問は最小限（最大 {qpol.get('max_questions',2)} 問）。
- 『やり返す』は原則として提示しません。
- {priorities_line}
- 文体規則: スタイル={tone.get('style','敬体・簡潔・論理')}、語尾の禁止={tone.get('avoid_endings',['だ'])}、引用=強調:{quotes.get('emphasis','『』')}/会話:{quotes.get('speech','「」')}
"""
    values = f"""
価値観:
- 統制の焦点: {doctrines.get('control_scope','')}
- 理想と現実: {ideals.get('rule','')}
- 期待＝仮説: {expol.get('validation','')}
- 環境設計: {env.get('principle','')}（構成要素: {', '.join(env.get('components', []))}）
- 普遍正義は前提にしない。ケースごとに根拠ベースで最適化する。
"""
    stages = """
段階制:
- S0（驚き/初回限定）: [cold_read|binary_opposition|unsent_message|sim_48h|premise_inventory|forbidden_guard|other_view] のいずれか1つで洞察1行＋確認1問。
- S1（要約＋前提確認）: 30〜60字で要約→不足前提を最重要1点のみ質問。
- S2（構造化）: 因果の鎖で論点2〜3点。統制可能/不可能を分離。質問は最大1。
- S3（選択肢）: 2〜3案（利点/リスク/必要リソース）。環境設計を第1選択肢に。
- S4（次アクション）: 判断軸を示し、次の一歩を具体化。必要に応じて仲介AI提案。
"""
    schema = """
出力は必ずJSONで返す（本文は assistant_message）。
{
  "assistant_message": "本文（敬体）",
  "next_stage": "S0|S1|S2|S3|S4",
  "asked_questions": [],
  "tags": [],
  "surprise_type": "cold_read|binary_opposition|unsent_message|sim_48h|premise_inventory|forbidden_guard|other_view|null",
  "notes": "内部メモ（任意）"
}
"""
    return core + values + stages + schema

def build_messages(sess: dict, user_text: str):
    history = sess.get("history", [])
    trimmed = history[-4:] if len(history) > 4 else history[:]
    stage = sess.get("stage", "S1")
    domain = classify_domain(user_text)
    hint = f"[現在ステージ:{stage} / domain:{domain} / used_surprise={sess.get('used_surprise', False)}]"
    guidance = playbook_hint(domain, stage)

    msgs = [
        {"role": "system", "content": build_system_prompt(sess) + ("\n" + guidance if guidance else "")},
        {"role": "user", "content": hint},
    ]
    msgs.extend(trimmed)
    msgs.append({"role": "user", "content": user_text})
    return msgs

# =========================
# 生成
# =========================
def run_consult_ai(push_to: str, user_text: str) -> str:
    # 危機語が入っていたら安全運転へ
    flags = scan_redflags(user_text)
    if flags.get("crisis"):
        return "安全確保を最優先にしてください。今は助言より保護が重要です。必要であれば地域の公的相談窓口や110/119等の緊急連絡に繋いでください。落ち着いたら現実/理想/ギャップ/対応を一緒に整理しましょう。"

    sess = get_session(push_to)
    if sess["stage"] == "S0" and sess.get("used_surprise"):
        sess["stage"] = "S1"

    messages = build_messages(sess, user_text)

    start = time.time()
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        app.logger.error("JSON parse failed; fallback to plain text.\n" + traceback.format_exc())
        resp2 = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.5,
        )
        text = resp2.choices[0].message.content.strip()
        # 安全側の自動遷移
        if   sess["stage"] == "S0": next_stage = "S1"
        elif sess["stage"] == "S1": next_stage = "S2"
        elif sess["stage"] == "S2": next_stage = "S3"
        else:                       next_stage = "S4"
        data = {
            "assistant_message": text,
            "next_stage": next_stage,
            "asked_questions": [],
            "tags": [],
            "surprise_type": "null",
            "notes": "fallback"
        }
    finally:
        record_elapsed(time.time() - start)

    # セッション更新
    assistant_message = data.get("assistant_message", "").strip()
    next_stage = data.get("next_stage", sess["stage"])
    tags = data.get("tags", [])
    if "surprise" in tags:
        sess["used_surprise"] = True

    valid = {"S0","S1","S2","S3","S4"}
    if next_stage not in valid:
        next_stage = "S1" if sess["stage"]=="S0" else ("S2" if sess["stage"]=="S1" else "S3")
    sess["stage"] = next_stage

    sess["history"].append({"role": "user", "content": user_text})
    sess["history"].append({"role": "assistant", "content": assistant_message})
    if len(sess["history"]) > 10:
        sess["history"] = sess["history"][-10:]

    # 仕上げ
    assistant_message = sanitize(assistant_message)
    closers = (get_phrasebank() or {}).get("closers", [])
    if next_stage == "S4" or closers:
        tail = closers[0] if closers else "ここまでで足りない前提があれば教えてください。"
        assistant_message += "\n\n" + tail
    return assistant_message

# =========================
# ルーティング
# =========================
@app.get("/")
def health():
    return "ok", 200

@app.post("/callback")
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature"); abort(400)
    except Exception as e:
        app.logger.error(f"Webhook handle error: {e}\n{traceback.format_exc()}"); abort(400)
    return "OK"

# =========================
# イベントハンドラ（重複排除＋待機閾値＋reply/push切替）
# =========================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: MessageEvent):
    user_text = event.message.text
    reply_token = event.reply_token
    push_to = get_push_target(event)

    # 重複イベントの抑止（早期リターン）
    key = _event_key(event)
    now = time.time()
    _purge_odict(processed_events, DEDUP_TTL)
    ent = processed_events.get(key)
    if ent:
        if ent["state"] == "done":
            app.logger.info(f"dedup: skip already-done event key={key}")
            return
        if now - ent["ts"] < INFLIGHT_GRACE:
            app.logger.info(f"dedup: skip inflight duplicate key={key}")
            return
        else:
            app.logger.info(f"dedup: inflight expired; reprocess key={key}")
    processed_events[key] = {"state": "inflight", "ts": now}

    result = {"text": None, "error": None}
    done = threading.Event()

    def worker():
        try:
            result["text"] = run_consult_ai(push_to, user_text)
        except Exception as e:
            result["error"] = e
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True).start()

    wait_sec = current_timeout()
    if done.wait(timeout=wait_sec):
        text = result["text"] if result["text"] else "申し訳ありません。内部でエラーが発生しました。もう一度お試しください。"
        try:
            line_bot_api.reply_message(reply_token, TextSendMessage(text=text))
            processed_events[key] = {"state": "done", "ts": time.time()}
        except Exception as e:
            app.logger.error(f"reply_message failed: {e}\n{traceback.format_exc()}")
    else:
        try:
            line_bot_api.reply_message(reply_token, TextSendMessage(text="少しお待ちください…AsaokaAIが考えています。"))
        except Exception as e:
            app.logger.error(f"reply (placeholder) failed: {e}\n{traceback.format_exc()}")

        def pusher():
            done.wait()
            final = result["text"] if result["text"] else "お待たせしました。内部エラーが発生しました。もう一度送ってください。"
            if push_to and _should_push(push_to, final):
                try:
                    line_bot_api.push_message(push_to, TextSendMessage(text=final))
                except Exception as e:
                    app.logger.error(f"push_message failed: {e}\n{traceback.format_exc()}")
            else:
                app.logger.info("dedup: push skipped or target missing")
            processed_events[key] = {"state": "done", "ts": time.time()}

        threading.Thread(target=pusher, daemon=True).start()

# =========================
# ローカル実行（Renderでは不要）
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
