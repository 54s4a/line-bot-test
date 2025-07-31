from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = '4Vgr8OrFclaBUiWAYp6Z6d0X8SH/hRBglSqOmHYBcu/7eVpKZo9Gle9cgbN1cnSBAaOL9GKCca0hNRET9HeIEeT8YuExsYZ5oLrx1iV/pgPIdr9WlXfOHODM7Vbqo5H5U1ABLZPV06BPLaKr8iqECwdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '9d2f67e19341f7d1c415654dfde69c26'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    received_text = event.message.text
    reply_text = f"受け取りました：「{received_text}」"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()
