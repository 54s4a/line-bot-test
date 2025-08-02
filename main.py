import os
from flask import Flask, request, abort
from dotenv import load_dotenv
import openai
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 環境変数の読み込み
load_dotenv()
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
openai.api_key = os.getenv('OPENAI_API_KEY')

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
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.7,
            max_tokens=600
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return "ChatGPTへの接続に失敗しました。APIキーまたはモデル設定をご確認ください。"

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

# 起動用（Renderでは不要な場合もあり）
# if __name__ == "__main__":
#     app.run()

