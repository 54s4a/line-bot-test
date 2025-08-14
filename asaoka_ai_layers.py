# -*- coding: utf-8 -*-
# ====== asaoka_ai_layers.py ======
# 相談AI「思想レイヤー分離」LLMハイブリッド版
# - route() で分類（ルール）
# - gen_core / gen_neutral / gen_ops は LLM で生成（形式強制）
# - 失敗時はテンプレにフォールバック
# 使い方: main.py から generate_reply() を呼ぶだけ

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

# ===== 設定 =====
USE_LLM = True  # False にすると完全テンプレモード
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # Render環境変数に設定

# ===== LLM クライアント（必要時のみ import）=====
_client = None
def _get_client():
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY が未設定です。Renderの環境変数に設定してください。")
        from openai import OpenAI
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client

# ========== データ構造 ==========

@dataclass
class Meta:
    domain: str       # 職場/恋愛/家族/友人/金銭/契約/SNS/その他
    temp: str         # 低/中/高
    goal: str         # 意思決定/言語化/謝罪/交渉/境界線設定/記録化/その他
    surprise: str     # 相手視点翻訳 / 48時間 / 隠れ前提棚卸し

@dataclass
class OpsLayer:
    checks: List[str]
    actions: List[Dict]
    templates: Dict[str, str]

# ========== ルーター（ルールベース） ==========

DOMAIN_KEYWORDS = {
    "職場": ["上司","部下","同僚","シフト","残業","就業","評価","職務","配分","割当","会議","LINEグループ","稟議","資料","会議資料"],
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
        if any(k in text for k in TEMP_KEYWORDS["高"]):
            return "高"
        if any(k in text for k in TEMP_KEYWORDS["中"]):
            return "中"
        return "低"

    def find_goal():
        for g, kws in GOAL_KEYWORDS.items():
            if any(k in text for k in kws):
                return g
        return "交渉"

    domain = find_domain()
    temp = find_temp()
    goal = find_goal()

    if temp == "高":
        surprise = "相手視点翻訳"
    elif goal == "意思決定":
        surprise = "48時間"
    else:
        surprise = "隠れ前提棚卸し"

    return Meta(domain=domain, temp=temp, goal=goal, surprise=surprise)

# ========== テンプレ（フォールバック用） ==========

def _surprise_hook_text(meta: Meta) -> str:
    if meta.surprise == "相手視点翻訳":
        return (
            "【相手視点の仮訳】\n"
            "相手は『自分の緊急性』を最優先にしているかもしれません。\n"
            "こちらの負担や担当範囲が十分に考慮されていない可能性があります。"
        )
    if meta.surprise == "48時間":
        return (
            "【48時間シミュレーター】\n"
            "48時間後の自分が後悔しないのは、どの選択でしょうか。\n"
            "短期の空気より『線引きの明文化』を残せるかで考えてみてください。"
        )
    return (
        "【隠れ前提の棚卸し】\n"
        "『断る＝関係が壊れる』という前提を一度疑ってみましょう。\n"
        "実際は『断り方の言語』が関係の質を左右します。"
    )

def _fallback_core(meta: Meta, text: str) -> str:
    return (
        "【核】\n"
        "結論を出す前に、前提の置き場を見直す必要があります。\n\n"
        f"{_surprise_hook_text(meta)}\n\n"
        "短期の安心と長期のコストは、いつも交換条件になります。\n"
        "判断基準を『メリット＝将来の損得』にそろえ、\n"
        "どこまでやるか（やらないか）の線引きを、言葉で固定しましょう。"
    )

def _fallback_neutral(meta: Meta, text: str) -> str:
    if meta.domain == "SNS":
        return (
            "【中立】\n"
            "関係を悪化させず負担を減らす選択肢は、次の三つです。\n\n"
            "A) 事実のみを一度だけ短く返信する（煽らない・議論を拡張しない）。\n"
            "B) 返信はせず、記録化と通報・ミュート・キーワード非表示で被害を最小化する。\n"
            "C) 誤情報が広がる場合は、固定ポストで訂正文を出し、以降はそこに誘導する。"
        )
    if meta.domain == "職場":
        return (
            "【中立】\n"
            "関係を保ちつつ負担を減らす選択肢は、次の三つです。\n\n"
            "A) 一時的に対応する。ただし、次回以降の条件を明文化する。\n"
            "B) 今回は断る。代わりの案（時期・方法・担当）を提示する。\n"
            "C) 第三者判断に委ねる。個人対立を避け、配分を客観化する。"
        )
    return (
        "【中立】\n"
        "負担を減らしつつ関係を保つ選択肢は、次の三つです。\n\n"
        "A) いまは応じるが、次回以降の条件を明記する。\n"
        "B) 今回は断り、代替案（タイミング・方法）を示す。\n"
        "C) 第三者レビューに回して個人対立を避ける。"
    )

def _fallback_ops(meta: Meta, text: str) -> OpsLayer:
    if meta.domain == "SNS":
        checks = [
            "対象ポスト/スレッドのURL・ユーザーID・時刻を記録（スクショも保存）",
            "内容の重大度分類：批判/誹謗中傷/脅迫/個人情報/営業妨害",
            "相手の影響力（フォロワー/拡散速度）と想定被害範囲を把握",
            "訂正すべき事実があるか（ソースの有無・自分の非の有無）",
        ]
        actions = [
            {"step":"記録化","how":"URL・スクショ等を1箇所に集約","success":"第三者が再現可能","risk":"証拠抜け","eta":"10分"},
            {"step":"初回レス草案","how":"事実のみ125字以内で一度だけ返信","success":"延焼抑制","risk":"泥沼化","eta":"15分"},
            {"step":"プラットフォーム運用","how":"通報/ミュート/非表示の組み合わせ","success":"可視被害最小化","risk":"過剰ブロック","eta":"5分"},
            {"step":"必要ならエスカレーション","how":"法務/警察/窓口へ証拠と共に報告","success":"対応の速さと保全","risk":"通報先誤り","eta":"10分"},
        ]
        templates = {"message":"ご指摘ありがとうございます。事実関係は以下のとおりです。誤解があれば修正します。詳しくは固定ポストをご参照ください。"}
        return OpsLayer(checks=checks, actions=actions, templates=templates)

    if meta.domain == "職場":
        checks = ["依頼の種類（指示かお願いか）を確認","相手の権限を確認","職務範囲の文面を添付"]
        actions = [
            {"step":"記録化","how":"経緯をメモ化","success":"第三者再現可能","risk":"感情語混入","eta":"10分"},
            {"step":"返信","how":"条件付き合意を提示","success":"条件明確化","risk":"既成事実化","eta":"15分"}
        ]
        templates = {"message":"本件、緊急性は理解しております。担当範囲外のため『本日◯分・次回は上長判断で配分』を条件にお願いできますか。難しい場合は上長のご判断をお願いします。"}
        return OpsLayer(checks=checks, actions=actions, templates=templates)

    checks = ["相手の要件（目的・期日・成果）確認","自分の許容上限（時間・頻度）の言語化"]
    actions = [
        {"step":"記録化","how":"要件/履歴/合意条件を集約","success":"第三者再現可能","risk":"抜け漏れ","eta":"10分"},
        {"step":"返答","how":"条件付き合意か代替案の提示","success":"合意条件の明確化","risk":"玉虫色表現","eta":"10分"}
    ]
    templates = {"message":"本件の目的と期日を確認し、対応可能な範囲を以下に記します。必要あれば再調整しましょう。"}
    return OpsLayer(checks=checks, actions=actions, templates=templates)

# ========== LLM 生成ヘルパ ==========

SYSTEM_PROMPT = (
    "あなたは『メリットの法則』を軸にする相談AIです。敬体。断定しすぎない。"
    "見出しは【核】【中立】【実務】【一体化まとめ】【次の一手】を使う。"
    "必ず見出しの直後で改行する。箇条書きは行頭にA) / B) / C) などを置き1行ずつにする。"
    "実務はチェック/アクション/テンプレの順。各アクションに（所要時間）を入れる。"
    "全体は短文で改行多め。"
)

def _call_llm(meta: Meta, user_text: str, section: str, extra_notes: str = "") -> str:
    """
    section: 'core' | 'neutral' | 'ops'
    """
    client = _get_client()
    user_prompt = f"""
【前提】
domain={meta.domain} / temp={meta.temp} / goal={meta.goal} / surprise={meta.surprise}
ユーザー原文：{user_text}

【目的】
'{section}' セクションの本文のみを生成してください。

【書式・必須ルール】
- 見出し→改行→本文。見出しは次を使用:
  core=【核】, neutral=【中立】, ops=【実務】
- 文は短め。段落は意味ごとに改行。
- 箇条書きは A) / B) / C) の行頭記法を使い、各項目は1行。
- 実務では「チェック：」「アクション：」「テンプレ：」の順。
- 日本語、丁寧語。比喩は最小限。専門用語は避ける。

【ドメイン注意】
- 職場: 権限・担当範囲・配分。個人対立よりプロセス重視。
- SNS: URL/スクショ保存、重大度分類、一度だけ事実訂正、通報・非表示、固定ポスト誘導。
- 契約: 期日、条項、記録化、通知手順。
- 恋愛/友人: 境界線、頻度、タイミング、第三者冷却。

{extra_notes}
"""
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.3,
        max_tokens=600,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt.strip()}
        ]
    )
    return resp.choices[0].message.content.strip()

# ========== レイヤー生成（LLM or フォールバック） ==========

def gen_core(meta: Meta, text: str) -> str:
    if USE_LLM:
        try:
            return _call_llm(meta, text, "core", "冒頭に『結論を出す前に、前提の置き場を見直す必要があります。』を含める。")
        except Exception:
            pass
    return _fallback_core(meta, text)

def gen_neutral(meta: Meta, text: str) -> str:
    if USE_LLM:
        try:
            return _call_llm(meta, text, "neutral")
        except Exception:
            pass
    return _fallback_neutral(meta, text)

def gen_ops(meta: Meta, text: str) -> OpsLayer:
    if USE_LLM:
        try:
            raw = _call_llm(meta, text, "ops", "各アクションに（○分）の所要時間を必ず入れる。")
            # LLM版では実務はプレーンテキストで返し、integrateでそのまま差し込むため
            # 既定の入れ物に流し込む
            checks = []
            actions = []
            template_text = ""
            # 簡易パーサ（'チェック：' 'アクション：' 'テンプレ：' を行頭で探す）
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            # 見出しは除去
            if lines and lines[0].startswith("【実務】"):
                lines = lines[1:]
            mode = None
            for ln in lines:
                if ln.startswith("チェック"):
                    mode = "checks"; continue
                if ln.startswith("アクション"):
                    mode = "actions"; continue
                if ln.startswith("テンプレ"):
                    mode = "template"; continue
                if mode == "checks":
                    checks.append(ln.lstrip("- ・"))
                elif mode == "actions":
                    actions.append({"step": ln, "how": "", "success": "", "risk": "", "eta": ""})
                elif mode == "template":
                    template_text += (ln + "\n")
            if not checks and not actions:
                raise ValueError("parse fail")
            return OpsLayer(checks=checks, actions=actions, templates={"message": template_text.strip() or "——"})
        except Exception:
            pass
    # 失敗時
    return _fallback_ops(meta, text)

# ========== 出力統合 ==========

def integrate(meta: Meta, core: str, neutral: str, ops: OpsLayer) -> str:
    # 実務レイヤーの整形（行ごとに改行）
    ops_lines = ["【実務】"]
    if ops.checks:
        ops_lines.append("チェック：")
        for c in ops.checks:
            ops_lines.append(f"- {c}")
    if ops.actions:
        ops_lines.append("アクション：")
        for a in ops.actions:
            ops_lines.append(f"- {a['step']}")
    if ops.templates.get("message"):
        ops_lines.append("テンプレ：")
        ops_lines.append(ops.templates["message"])

    summary = (
        "【一体化まとめ】\n"
        "短期の雰囲気は、将来のコストとトレードになります。\n"
        "引き受けるなら条件を価格として明示し、断るなら代替案と第三者判断の導線を置きましょう。\n"
        "どちらにせよ、言葉で線引きを固定して自分のメリットを守ることが大切です。"
    )
    next_moves = (
        "【次の一手】\n"
        "・今：上のテンプレを整えて返信（15分）\n"
        "・今日：依頼/事象ログを記録（5分）\n"
        "・今週：配分や運用ルールの明文化を提案（10分）"
    )

    return "\n\n".join([core, neutral, "\n".join(ops_lines), summary, next_moves])

# ========== 公開関数 ==========

def generate_reply(user_text: str) -> Dict:
    meta = route(user_text)
    core = gen_core(meta, user_text)
    neutral = gen_neutral(meta, user_text)
    ops = gen_ops(meta, user_text)
    final_text = integrate(meta, core, neutral, ops)
    return {
        "meta": meta.__dict__,
        "layers": {
            "core": core,
            "neutral": neutral,
            "ops": {
                "checks": ops.checks,
                "actions": ops.actions,
                "templates": ops.templates
            }
        },
        "final": final_text
    }
