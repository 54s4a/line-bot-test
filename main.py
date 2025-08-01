import os
import openai
from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import openai

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

app = Flask(__name__)
user_stage_map = {}

def get_system_prompt(stage):
    if stage == 1:
        return "あなたは相談対応のAIです。相手がどのような状況で困っているかを聞き出してください。寄り添いながら事実を丁寧に把握してください。"
    elif stage == 2:
        return "あなたは相談対応のAIです。相手がそのような状況に至った背景や動機を整理する手助けをしてください。"
    elif stage == 3:
        return "あなたは相談対応のAIです。相手が前向きな行動をとれるように、今後の選択肢や視点を提示してください。"
    else:
        return "相談は完了しましたが、必要であればいつでも続きに応じます。"

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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()

    if user_text.lower() in ['リセット', 'reset', '初期化']:
        user_stage_map[user_id] = 1
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="ステージをリセットしました。最初から再開します。")
        )
        return

    stage = user_stage_map.get(user_id, 1)
    reply_text = generate_reply(stage, user_text)

    if stage < 3:
        user_stage_map[user_id] = stage + 1
    else:
        user_stage_map.pop(user_id, None)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
