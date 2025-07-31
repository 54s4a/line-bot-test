from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = '4Vgr8OrFclaBUiWAYp6Z6d0X8SH/hRBglSqOmHYBcu/7eVpKZo9Gle9cgbN1cnSBAaOL9GKCca0hNRET9HeIEeT8YuExsYZ5oLrx1iV/pgPIdr9WlXfOHODM7Vbqo5H5U1ABLZPV06BPLaKr8iqECwdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '9d2f67e19341f7d1c415654dfde69c26'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ユーザーごとのステージを一時管理（本番ではRedis等を推奨）
user_stage_map = {}

# ステージごとの応答テンプレート（Ver1）
TEMPLATES = {
    1: "まず、事実確認をさせてください。\n\n今、どのような状況で、何が起きていると感じていますか？できる範囲で構いませんので、具体的に教えてください。",
    2: "ありがとうございます。では、そう感じるに至った背景や、これまでの経緯があれば教えてください。\n\n「なぜそうなってしまったと思うか」や「相手の反応や行動」などが分かると助かります。",
    3: "承知しました。\n\n今後どうしたいか、またどうすれば納得できる方向に近づけると思うか、一緒に考えてみましょう。\n必要であれば、いくつか視点を提示させていただきます。",
    'end': "ご相談ありがとうございます。\nもし引き続き話したい内容があれば、またいつでも送ってください。"
}

# Webhook受信エンドポイント
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# メッセージ受信イベント
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()

    # ステージ未登録なら1から開始
    stage = user_stage_map.get(user_id, 1)

    if user_text.lower() in ['リセット', 'reset', '初期化']:
        user_stage_map[user_id] = 1
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="ステージをリセットしました。最初から再開します。\n\n" + TEMPLATES[1])
        )
        return

    # 応答とステージ遷移
    if stage == 1:
        reply = TEMPLATES[1]
        next_stage = 2
    elif stage == 2:
        reply = TEMPLATES[2]
        next_stage = 3
    elif stage == 3:
        reply = TEMPLATES[3]
        next_stage = 'end'
    else:
        reply = TEMPLATES['end']
        next_stage = 'end'

    # ステージ保存
    if next_stage != 'end':
        user_stage_map[user_id] = next_stage
    else:
        user_stage_map.pop(user_id, None)  # 終了後は削除

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
if __name__ == "__main__":
    app.run()
