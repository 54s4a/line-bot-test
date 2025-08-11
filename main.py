import os
from flask import Flask, request, abort
from dotenv import load_dotenv
from openai import OpenAI
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 環境変数の読み込み
load_dotenv()
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

app = Flask(__name__)

# プロンプトの土台
def get_system_prompt(stage):
    if stage == "default":
        return "あなたは丁寧なアシスタントです。ユーザーの問いに対して親切に答えてください。"
    # 他のstage条件を追加可能
    return "適切なステージが設定されていません。"

# ChatGPTの応答を生成
def generate_reply(stage, user_input):
    system_prompt = get_system_prompt(stage)
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",  # 必要に応じて "gpt-4o" に変更可
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_input},
            ],
            temperature=0.7,
            max_tokens=600,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        app.logger.exception(f"OpenAI error: {e}")
        return "ごめん、内部でエラーが出てる。少し待ってもう一度送って。"

# LINEからのWebhook
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Check LINE_CHANNEL_SECRET.")
        abort(400)
    except Exception as e:
        app.logger.error(f"Error in /callback: {e}")
        abort(500)

    return 'OK'

# メッセージ受信時の処理
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_input = event.message.text
    stage = "default"  # 必要に応じて切り替えロジックを実装
    reply_text = generate_reply(stage, user_input)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

# 末尾にこれを入れる/コメント解除する
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))  # Renderが渡すPORTで待受
    app.run(host="0.0.0.0", port=port)

