# -*- coding: utf-8 -*-
# ====== asaoka_ai_layers.py ======
# 相談AI「思想レイヤー分離」ミニ実装（読みやすい改行＆やや口語寄り）
# main.py から generate_reply() を呼ぶだけで動作します。

from dataclasses import dataclass
from typing import Dict, List

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

# ========== ルーター ==========

DOMAIN_KEYWORDS = {
    "職場": ["上司","部下","同僚","シフト","残業","就業","評価","職務","配分","割当","会議","LINEグループ","稟議"],
    "恋愛": ["恋人","デート","連絡","距離","告白","依存","浮気","結婚","破局"],
    "契約": ["契約","条項","違反","通知書","内容証明","労基","労働基準","コンプライアンス"],
    "SNS": ["SNS","X","インスタ","ティックトック","コメント","DM","拡散","炎上"]
}

TEMP_KEYWORDS = {
    "高": ["今すぐ","責任取れ","無理","怖い","訴える","殺す","潰す","二度と","完全に"],
    "中": ["困る","迷惑","厳しい","緊急","早急","納得できない","不安"],
}

GOAL_KEYWORDS = {
    "交渉": ["条件","合意","妥協","配分","割当","提案","折衷"],
    "境界線設定": ["線引","限度","担当外","距離","拒否","断る"],
    "記録化": ["記録","メモ","保存","証拠","議事録","履歴"],
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

# ========== レイヤー生成 ==========

def _surprise_hook(meta: Meta) -> str:
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

def gen_core(meta: Meta, text: str) -> str:
    # 見出し→空行→本文（短文を改行で区切る／やや口語）
    return (
        "【核】\n"
        "結論を出す前に、前提の置き場を見直す必要があります。\n\n"
        f"{_surprise_hook(meta)}\n\n"
        "短期の安心と長期のコストは、いつも交換条件になります。\n"
        "判断基準を『メリット＝将来の損得』にそろえ、\n"
        "どこまでやるか（やらないか）の線引きを、言葉で固定しましょう。"
    )

def gen_neutral(meta: Meta, text: str) -> str:
    # 箇条書きは行頭改行＆単文で読みやすく
    return (
        "【中立】\n"
        "関係を保ちつつ負担を減らす選択肢は、次の三つです。\n\n"
        "A) 一時的に対応する。ただし、次回以降の条件を明文化する。\n"
        "B) 今回は断る。代わりの案（時期・方法・担当）を提示する。\n"
        "C) 第三者判断に委ねる。個人対立を避け、配分を客観化する。"
    )

def gen_ops(meta: Meta, text: str) -> OpsLayer:
    # 実務は既存の改行形式を維持（読みやすさ良好）
    checks = [
        "依頼の種類（指示かお願いか）を確認",
        "相手の権限を確認",
        "職務範囲の文面を添付"
    ]
    actions = [
        {
            "step": "記録化",
            "how": "経緯をメモに残す",
            "success": "第三者が再現可能",
            "risk": "感情語の混入",
            "eta": "10分"
        },
        {
            "step": "返信",
            "how": "条件付き合意を提示",
            "success": "条件明確化",
            "risk": "即時対応の既成事実化",
            "eta": "15分"
        }
    ]
    templates = {
        "message": (
            "本件、緊急性は理解しております。担当範囲外のため、対応する場合は「本日◯分・"
            "次回は上長判断で配分」を条件にお願いできますか。難しい場合は、上長のご判断をお願いします。"
        )
    }
    return OpsLayer(checks=checks, actions=actions, templates=templates)

def integrate(meta: Meta, core: str, neutral: str, ops: OpsLayer) -> str:
    # 実務レイヤーの整形（行ごとに改行）
    ops_lines = ["【実務】"]
    ops_lines.append("チェック：")
    for c in ops.checks:
        ops_lines.append(f"- {c}")
    ops_lines.append("アクション：")
    for a in ops.actions:
        ops_lines.append(f"- {a['step']}（{a['eta']}）")
        ops_lines.append(f"  ・やり方：{a['how']}")
        ops_lines.append(f"  ・成功条件：{a['success']}")
        ops_lines.append(f"  ・リスク：{a['risk']}")
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
        "・今日：依頼ログを記録（5分）\n"
        "・今週：配分ルールの明文化を上長に提案（10分）"
    )

    # 段落は二重改行で区切る。段落内は任意の改行を保持。
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
