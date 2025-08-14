# -*- coding: utf-8 -*-
# ====== asaoka_ai_layers.py ======
# 相談AI「思想レイヤー分離」ミニ実装（ルールベース最小版）
# 依存なし。main.py から generate_reply() を呼ぶだけで動作します。

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
        return "【相手視点の仮訳】相手は『自分の緊急性』を最優先にし、あなたの負担や担当範囲を十分に評価していない可能性があります。"
    if meta.surprise == "48時間":
        return "【48時間シミュレーター】48時間後のあなたが後悔しない選択肢は何かを考えてください。"
    return "【隠れ前提の棚卸し】『断る＝関係が壊れる』という前提を疑ってください。"

def gen_core(meta: Meta, text: str) -> str:
    return f"【核】結論を出す前に、前提の置き場を変える必要があります。{_surprise_hook(meta)} 短期の安心と長期のコストは常にトレードです。価値判断を『メリット＝将来の損得』で評価し直し、線引きを言語で固定してください。"

def gen_neutral(meta: Meta, text: str) -> str:
    return "【中立】関係を保ちつつ負担を下げる選択肢は次の三つです。A）一時的に対応するが次回以降の条件を明文化する。B）今回は断り代替案を提示する。C）第三者判断に委ねる。"

def gen_ops(meta: Meta, text: str) -> OpsLayer:
    checks = ["依頼の種類（指示かお願いか）を確認", "相手の権限を確認", "職務範囲の文面を添付"]
    actions = [
        {"step": "記録化", "how": "経緯をメモに残す", "success": "第三者が再現可能", "risk": "感情語混入", "eta": "10分"},
        {"step": "返信", "how": "条件付き合意を提示", "success": "条件明確化", "risk": "既成事実化", "eta": "15分"}
    ]
    templates = {"message": "本件、緊急性は理解しております。担当範囲外のため条件付きで対応可能です。"}
    return OpsLayer(checks=checks, actions=actions, templates=templates)

def integrate(meta: Meta, core: str, neutral: str, ops: OpsLayer) -> str:
    ops_lines = ["【実務】"]
    ops_lines.append("チェック：" + "　".join(ops.checks))
    ops_lines.append("アクション：" + "　".join([f"{a['step']}({a['eta']})" for a in ops.actions]))
    ops_lines.append("テンプレ：" + ops.templates["message"])
    summary = "【一体化まとめ】短期の雰囲気は将来のコストとトレード。条件を明示し文書化を。"
    next_moves = "【次の一手】・今：返信送信（15分）・今日：記録（5分）・今週：配分ルール提案（10分）"
    return "\n\n".join([core, neutral, "\n".join(ops_lines), summary, next_moves])

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
