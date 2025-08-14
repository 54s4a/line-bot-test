# -*- coding: utf-8 -*-
# ===== asaoka_ai_layers.py =====
# 役割：入力をルーティング→各レイヤー生成→最終整形。HTTP/LINEのimportは禁止。

import os, re
from dataclasses import dataclass
from typing import Dict, List

# --- LLM設定（無ければ自動フォールバック） ---
USE_LLM = os.environ.get("USE_LLM", "1") != "0"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

_client = None
def _get_client():
    """OpenAI SDK or KEY が無い/失敗したら None を返す（落とさない）"""
    global _client
    if _client is not None:
        return _client
    try:
        from openai import OpenAI
    except Exception:
        return None
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        _client = OpenAI(api_key=key)
        return _client
    except Exception:
        return None

# --- データ構造 ---
@dataclass
class Meta:
    domain: str
    temp: str
    goal: str
    surprise: str

@dataclass
class OpsLayer:
    checks: List[str]
    actions: List[Dict]
    templates: Dict[str, str]

# --- ルーター ---
DOMAIN_KEYWORDS = {
    "職場": ["上司","部下","同僚","会議","資料","職務","配分","残業","稟議"],
    "契約": ["契約","条項","違反","内容証明","労基","法テラス","通知書"],
    "SNS": ["SNS","X","ツイッター","Twitter","インスタ","TikTok","炎上","DM","ポスト","投稿","コメント"],
    "恋愛": ["恋人","デート","告白","距離","依存","別れる"],
}
TEMP_KEYWORDS = {"高": ["今すぐ","訴える","責任取れ","至急","二度と"], "中": ["困る","緊急","厳しい","納得できない"]}
GOAL_KEYWORDS = {
    "交渉": ["条件","合意","妥協","配分","提案"],
    "境界線設定": ["線引","限度","担当外","拒否","断る"],
    "記録化": ["記録","メモ","証拠","議事録","履歴","スクショ"],
    "意思決定": ["決める","選ぶ","判断","優先","方針"],
}

def route(text: str) -> Meta:
    def pick(d: Dict[str, List[str]], default: str):
        for k, kws in d.items():
            if any(w in text for w in kws): return k
        return default
    domain = pick(DOMAIN_KEYWORDS, "その他")
    temp = "高" if any(w in text for w in TEMP_KEYWORDS["高"]) else ("中" if any(w in text for w in TEMP_KEYWORDS["中"]) else "低")
    goal = pick(GOAL_KEYWORDS, "交渉")
    surprise = "相手視点翻訳" if temp=="高" else ("48時間" if goal=="意思決定" else "隠れ前提棚卸し")
    return Meta(domain, temp, goal, surprise)

# --- テンプレ（フォールバック） ---
def _surprise(meta: Meta) -> str:
    if meta.surprise == "相手視点翻訳":
        return "【相手視点の仮訳】相手は自分の緊急性を最優先にしている可能性。こちらの負担が十分に考慮されていないかもしれません。"
    if meta.surprise == "48時間":
        return "【48時間シミュレーター】48時間後の自分が後悔しない選択を。『線引きの明文化』を優先。"
    return "【隠れ前提の棚卸し】『断る＝関係が壊れる』という前提を一度疑い、断り方の言語で関係を守る。"

def _fallback_core(meta: Meta) -> str:
    return ("【核】\n"
            "結論を出す前に、前提の置き場を見直す必要があります。\n"
            f"{_surprise(meta)}\n"
            "短期の安心と長期のコストは交換条件です。判断基準を『将来の損得』にそろえ、線引きを言葉で固定しましょう。")

def _fallback_neutral(meta: Meta) -> str:
    if meta.domain == "SNS":
        return ("【中立】\n"
                "A) 事実だけを一度だけ短く返信\n"
                "B) 返信せずに記録化・通報・ミュート・非表示\n"
                "C) 誤情報は固定ポストで訂正し、以後は誘導")
    if meta.domain == "職場":
        return ("【中立】\n"
                "A) 一時対応（次回条件を明文化）\n"
                "B) 断って代替案を提示\n"
                "C) 第三者判断に委ねて配分を客観化")
    return ("【中立】\n"
            "A) 今は応じるが次回条件を明記\n"
            "B) 今回は断り代替案を提示\n"
            "C) 第三者レビューに回す")

def _fallback_ops(meta: Meta) -> OpsLayer:
    if meta.domain == "SNS":
        checks = ["URL/ID/時刻を記録（スクショ）","重大度分類（批判/中傷/脅迫/個人情報）","拡散度の把握","訂正すべき事実の有無"]
        actions = [
            {"step":"記録化（10分）","how":"証拠を1か所に集約","success":"第三者再現可能","risk":"証拠抜け"},
            {"step":"初回レス草案（15分）","how":"事実のみ125字以内・一度だけ","success":"延焼抑制","risk":"泥沼化"},
            {"step":"運用（5分）","how":"通報/ミュート/非表示","success":"可視被害最小化","risk":"過剰ブロック"},
            {"step":"必要ならエスカレ（10分）","how":"法務/警察/窓口へ証拠送付","success":"迅速対応","risk":"通報先誤り"},
        ]
        templates = {"message":"ご指摘ありがとうございます。事実関係は以下のとおりです。誤解があれば修正します。詳しくは固定ポストをご参照ください。"}
        return OpsLayer(checks, actions, templates)
    # 職場
    checks = ["依頼の種類（指示/お願い）","相手の権限","職務範囲の文面"]
    actions = [
        {"step":"記録化（10分）","how":"経緯をメモ化","success":"第三者再現可能","risk":"感情語混入"},
        {"step":"返信（15分）","how":"条件付き合意を提示","success":"条件明確化","risk":"既成事実化"},
    ]
    templates = {"message":"本件、緊急性は理解しております。担当範囲外のため、対応する場合は『本日◯分・次回は上長判断で配分』を条件にお願いできますか。"}
    return OpsLayer(checks, actions, templates)

# --- LLM呼び出し（あれば使う） ---
SYS_PROMPT = ("見出しは【核】【中立】【実務】。見出し直後に改行1回。空行は最小。"
              "箇条書きは A)/B)/C) で1行ずつ。実務は『チェック：』『アクション：』『テンプレ：』順。短文で。")

def _call_llm(meta: Meta, user_text: str, section: str, note: str = "") -> str:
    client = _get_client()
    if client is None:
        raise RuntimeError("llm_unavailable")
    prompt = f"""domain={meta.domain} / temp={meta.temp} / goal={meta.goal} / surprise={meta.surprise}
ユーザー原文：{user_text}
目的：{section}だけ生成。{note}"""
    resp = client.chat.completions.create(
        model=OPENAI_MODEL, temperature=0.3, max_tokens=600,
        messages=[{"role":"system","content":SYS_PROMPT},{"role":"user","content":prompt}]
    )
    return resp.choices[0].message.content.strip()

def gen_core(meta: Meta, text: str) -> str:
    if USE_LLM:
        try:
            return _call_llm(meta, text, "【核】", "冒頭に『結論を出す前に、前提の置き場を見直す必要があります。』を含める。")
        except Exception:
            pass
    return _fallback_core(meta)

def gen_neutral(meta: Meta, text: str) -> str:
    if USE_LLM:
        try:
            return _call_llm(meta, text, "【中立】")
        except Exception:
            pass
    return _fallback_neutral(meta)

def gen_ops(meta: Meta, text: str) -> OpsLayer:
    if USE_LLM:
        try:
            raw = _call_llm(meta, text, "【実務】", "実務では『チェック：』『アクション：』『テンプレ：』を必ず入れる。")
            lines = [l.strip() for l in raw.splitlines()]
            if lines and lines[0].startswith("【実務】"):
                lines = lines[1:]
            mode, checks, actions, template = None, [], [], ""
            for ln in lines:
                if ln.startswith("チェック"): mode="c"; continue
                if ln.startswith("アクション"): mode="a"; continue
                if ln.startswith("テンプレ"): mode="t"; continue
                if not ln: continue
                if mode=="c": checks.append(ln.lstrip("-・ "))
                elif mode=="a": actions.append({"step": ln})
                elif mode=="t": template += (ln + "\n")
            if checks or actions or template.strip():
                return OpsLayer(checks, actions, {"message": template.strip()})
        except Exception:
            pass
    return _fallback_ops(meta)

# --- 整形ユーティリティ（空行削減） ---
HEADS = ("【核】","【中立】","【実務】","【一体化まとめ】","【次の一手】")
def _tidy(s: str) -> str:
    s = re.sub(r"\n{3,}", "\n", s)
    for h in HEADS:
        s = re.sub(fr"{re.escape(h)}\n+", h + "\n", s)
    return s.strip()

def integrate(meta: Meta, core: str, neutral: str, ops: OpsLayer) -> str:
    lines = [core, neutral]
    o = ["【実務】"]
    if ops.checks:
        o += ["チェック："] + [f"- {c}" for c in ops.checks]
    if ops.actions:
        o += ["アクション："] + [f"- {a['step']}" for a in ops.actions]
    if ops.templates.get("message"):
        o += ["テンプレ：", ops.templates["message"]]
    summary = "【一体化まとめ】\n短期の雰囲気は将来のコストとトレード。条件を明示し、第三者判断や代替案の導線を置きましょう。"
    nexts = "【次の一手】\n・今：テンプレ調整→返信（15分）\n・今日：記録を残す（5分）\n・今週：配分/運用ルールの明文化（10分）"
    out = "\n\n".join([_tidy(x) for x in [core, neutral, "\n".join(o), summary, nexts]])
    return _tidy(out)

# --- 公開関数 ---
def generate_reply(user_text: str) -> Dict:
    meta = route(user_text)
    core = gen_core(meta, user_text)
    neutral = gen_neutral(meta, user_text)
    ops = gen_ops(meta, user_text)
    final_text = integrate(meta, core, neutral, ops)
    return {
        "meta": meta.__dict__,
        "layers": {"core": core, "neutral": neutral,
                   "ops": {"checks": ops.checks, "actions": ops.actions, "templates": ops.templates}},
        "final": final_text
    }
