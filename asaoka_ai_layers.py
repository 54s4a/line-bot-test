# -*- coding: utf-8 -*-
# ====== asaoka_ai_layers.py ======
# 読みやすい最終整形（空行削減）＋SNS対応＋LLMハイブリッド

import os
import re
from dataclasses import dataclass
from typing import Dict, List

# ===== LLM設定 =====
USE_LLM = bool(os.environ.get("USE_LLM", "1"))  # "0"でオフ
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
_client = None
def _get_client():
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY が未設定です。")
        from openai import OpenAI
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client

# ===== データ構造 =====
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

# ===== ルーター =====
DOMAIN_KEYWORDS = {
    "職場": ["上司","部下","同僚","シフト","残業","就業","評価","職務","配分","割当","会議","稟議","資料","会議資料"],
    "恋愛": ["恋人","デート","連絡","距離","告白","依存","浮気","結婚","破局"],
    "契約": ["契約","条項","違反","通知書","内容証明","労基","労働基準","コンプライアンス"],
    "SNS": ["SNS","X","ツイッター","Twitter","インスタ","ティックトック","TikTok","コメント","DM","拡散","炎上","ポスト","投稿"]
}
TEMP_KEYWORDS = {
    "高": ["今すぐ","責任取れ","無理","怖い","訴える","殺す","潰す","二度と","完全に","至急","早くしろ"],
    "中": ["困る","迷惑","厳しい","緊急","早急","納得できない","不安"],
}
GOAL_KEYWORDS = {
    "交渉": ["条件","合意","妥協","配分","割当","提案","折衷"],
    "境界線設定": ["線引","限度","担当外","距離","拒否","断る","受けない"],
    "記録化": ["記録","メモ","保存","証拠","議事録","履歴","スクショ"],
    "謝罪": ["謝る","ごめん","すみません","お詫び"],
    "言語化": ["整理","言い換え","定義","構造化","フレーム"],
    "意思決定": ["決める","選ぶ","判断","優先","方針"]
}

def route(text: str) -> Meta:
    def find_domain():
        for d, kws in DOMAIN_KEYWORDS.items():
            if any(k in text for k in kws):
                return d
        return "その他"
    def find_temp():
        if any(k in text for k in TEMP_KEYWORDS["高"]): return "高"
        if any(k in text for k in TEMP_KEYWORDS["中"]): return "中"
        return "低"
    def find_goal():
        for g, kws in GOAL_KEYWORDS.items():
            if any(k in text for k in kws):
                return g
        return "交渉"

    domain = find_domain()
    temp = find_temp()
    goal = find_goal()
    surprise = "相手視点翻訳" if temp=="高" else ("48時間" if goal=="意思決定" else "隠れ前提棚卸し")
    return Meta(domain=domain, temp=temp, goal=goal, surprise=surprise)

# ===== テンプレ（フォールバック） =====
def _surprise_hook(meta: Meta) -> str:
    if meta.surprise == "相手視点翻訳":
        return "【相手視点の仮訳】相手は自分の緊急性を最優先にしているかもしれません。こちらの負担や担当範囲が十分に考慮されていない可能性があります。"
    if meta.surprise == "48時間":
        return "【48時間シミュレーター】48時間後の自分が後悔しない選択はどれか。短期の空気より『線引きの明文化』を優先しましょう。"
    return "【隠れ前提の棚卸し】『断る＝関係が壊れる』という前提を一度疑ってみましょう。鍵は『断り方の言語』です。"

def _fallback_core(meta: Meta, text: str) -> str:
    return (
        "【核】\n"
        "結論を出す前に、前提の置き場を見直す必要があります。\n"
        f"{_surprise_hook(meta)}\n"
        "短期の安心と長期のコストは交換条件です。判断基準を『メリット＝将来の損得』にそろえ、線引きを言葉で固定しましょう。"
    )

def _fallback_neutral(meta: Meta, text: str) -> str:
    if meta.domain == "SNS":
        return (
            "【中立】\n"
            "A) 事実のみを一度だけ短く返信（煽らない・議論を拡張しない）\n"
            "B) 返信せず、記録化と通報・ミュート・キーワード非表示で被害を最小化\n"
            "C) 誤情報が広がる場合は固定ポストで訂正文を出し、以降はそこに誘導"
        )
    if meta.domain == "職場":
        return (
            "【中立】\n"
            "A) 一時的に対応（次回以降の条件を明文化）\n"
            "B) 今回は断り、代替案（時期・方法・担当）を提示\n"
            "C) 第三者判断に委ねて配分を客観化"
        )
    return (
        "【中立】\n"
        "A) 今は応じるが、次回以降の条件を明記\n"
        "B) 今回は断り、代替案（タイミング・方法）を提示\n"
        "C) 第三者レビューに回して個人対立を回避"
    )

def _fallback_ops(meta: Meta, text: str) -> OpsLayer:
    if meta.domain == "SNS":
        checks = [
            "対象ポストのURL/ID/時刻を記録（スクショ保存）",
            "重大度分類：批判/誹謗中傷/脅迫/個人情報/営業妨害",
            "相手の影響力（拡散速度）と被害範囲の把握",
            "訂正すべき事実の有無（ソース/自分の非）",
        ]
        actions = [
            {"step":"記録化（10分）","how":"URL・スクショ等を1箇所に集約","success":"第三者が再現可能","risk":"証拠抜け"},
            {"step":"初回レス草案（15分）","how":"必要時のみ事実のみ125字以内で一度だけ返信","success":"延焼抑制","risk":"泥沼化"},
            {"step":"プラットフォーム運用（5分）","how":"通報/ミュート/非表示の組合せ","success":"可視被害最小化","risk":"過剰ブロック"},
            {"step":"必要ならエスカレーション（10分）","how":"法務/警察/窓口へ証拠と共に報告","success":"迅速対応・保全","risk":"通報先誤り"},
        ]
        templates = {"message":"ご指摘ありがとうございます。事実関係は以下のとおりです。誤解があれば修正します。固定ポストの説明をご参照ください。"}
        return OpsLayer(checks, actions, templates)
    if meta.domain == "職場":
        checks = ["依頼の種類（指示/お願い）","相手の権限","職務範囲の文面"]
        actions = [
            {"step":"記録化（10分）","how":"経緯をメモ化","success":"第三者再現可能","risk":"感情語混入"},
            {"step":"返信（15分）","how":"条件付き合意を提示","success":"条件明確化","risk":"既成事実化"},
        ]
        templates = {"message":"本件、緊急性は理解しております。担当範囲外のため、対応する場合は『本日◯分・次回は上長判断で配分』を条件にお願いできますか。"}
        return OpsLayer(checks, actions, templates)
    checks = ["要件（目的/期日/成果）確認","自分の許容上限（時間/頻度）の言語化"]
    actions = [
        {"step":"記録化（10分）","how":"要件/履歴/合意条件を集約","success":"第三者再現可能","risk":"抜け漏れ"},
        {"step":"返答（10分）","how":"条件付き合意または代替案提示","success":"合意条件の明確化","risk":"玉虫色表現"},
    ]
    templates = {"message":"本件の目的と期日を確認しました。対応可能な範囲を以下に記します。必要あれば再調整しましょう。"}
    return OpsLayer(checks, actions, templates)

# ===== LLM呼び出し =====
SYSTEM_PROMPT = (
    "『メリットの法則』に基づく相談AI。見出しは【核】【中立】【実務】のみ生成。"
    "見出し直後に改行1回。段落の空行は最小。箇条書きはA)/B)/C)等で1行ずつ。"
    "実務は「チェック：」「アクション：」「テンプレ：」の順。短文で簡潔に。"
)
def _call_llm(meta: Meta, user_text: str, section: str, extra: str = "") -> str:
    client = _get_client()
    prompt = f"""
【前提】domain={meta.domain} / temp={meta.temp} / goal={meta.goal} / surprise={meta.surprise}
【ユーザー原文】{user_text}
【目的】{section} セクションのみ生成。
【必須ルール】
- 見出し→改行1回→本文。空行は最小。
- 箇条書きは A) / B) / C) で1行ずつ。
- 実務では「チェック：」「アクション：」「テンプレ：」の見出しを含める。
【ドメイン注意】職場=権限/担当/配分。SNS=URL/スクショ/一度だけ事実訂正/通報・非表示/固定ポスト誘導。
{extra}
""".strip()
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.3,
        max_tokens=600,
        messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":prompt}]
    )
    return resp.choices[0].message.content.strip()

# ===== レイヤー生成 =====
def gen_core(meta: Meta, text: str) -> str:
    if USE_LLM:
        try:
            return _call_llm(meta, text, "【核】", "本文の冒頭に『結論を出す前に、前提の置き場を見直す必要があります。』を含める。")
        except Exception:
            pass
    return _fallback_core(meta, text)

def gen_neutral(meta: Meta, text: str) -> str:
    if USE_LLM:
        try:
            return _call_llm(meta, text, "【中立】")
        except Exception:
            pass
    return _fallback_neutral(meta, text)

def gen_ops(meta: Meta, text: str) -> OpsLayer:
    if USE_LLM:
        try:
            raw = _call_llm(meta, text, "【実務】", "各アクションに（◯分）など所要を含める。")
            # 簡易パース（不足時はフォールバック）
            lines = [l.strip() for l in raw.splitlines()]
            if lines and lines[0].startswith("【実務】"): lines = lines[1:]
            checks, actions, template = [], [], ""
            mode = None
            for ln in lines:
                if ln.startswith("チェック"): mode="c"; continue
                if ln.startswith("アクション"): mode="a"; continue
                if ln.startswith("テンプレ"): mode="t"; continue
                if not ln: continue
                if mode=="c": checks.append(ln.lstrip("-・ "))
                elif mode=="a": actions.append({"step": ln, "how":"", "success":"", "risk":""})
                elif mode=="t": template += (ln + "\n")
            if checks or actions or template.strip():
                return OpsLayer(checks, actions, {"message": template.strip()})
        except Exception:
            pass
    return _fallback_ops(meta, text)

# ===== 整形ユーティリティ（空行削減）=====
HEADING = ("【核】","【中立】","【実務】","【一体化まとめ】","【次の一手】")
def _tidy(text: str) -> str:
    # 3連以上の改行 → 1回
    text = re.sub(r"\n{3,}", "\n", text)
    # 見出し直後の余計な空行除去
    for h in HEADING:
        text = re.sub(fr"{re.escape(h)}\n+", h + "\n", text)
    # 末尾の余分な改行除去
    return text.strip()

# ===== 統合 =====
def integrate(meta: Meta, core: str, neutral: str, ops: OpsLayer) -> str:
    ops_lines = ["【実務】"]
    if ops.checks:
        ops_lines.append("チェック：")
        for c in ops.checks: ops_lines.append(f"- {c}")
    if ops.actions:
        ops_lines.append("アクション：")
        for a in ops.actions: ops_lines.append(f"- {a['step']}")
    if ops.templates.get("message"):
        ops_lines.append("テンプレ：")
        ops_lines.append(ops.templates["message"])
    summary = (
        "【一体化まとめ】\n"
        "短期の雰囲気は将来のコストとトレード。引き受けるなら条件を明示、断るなら代替案と第三者判断の導線を。"
    )
    next_moves = (
        "【次の一手】\n"
        "・今：上のテンプレを整えて返信（15分）\n"
        "・今日：記録を残す（5分）\n"
        "・今週：配分/運用ルールの明文化を提案（10分）"
    )
    final = "\n\n".join([core, neutral, "\n".join(ops_lines), summary, next_moves])
    return _tidy(final)

# ===== 公開関数 =====
def generate_reply(user_text: str) -> Dict:
    meta = route(user_text)
    core = gen_core(meta, user_text)
    neutral = gen_neutral(meta, user_text)
    ops = gen_ops(meta, user_text)
    final_text = integrate(meta, core, neutral, ops)
    return {
        "meta": meta.__dict__,
        "layers": {"core": core, "neutral": neutral, "ops": {"checks": ops.checks, "actions": ops.actions, "templates": ops.templates}},
        "final": final_text
    }
