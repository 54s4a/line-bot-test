import os, time, threading, traceback
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from openai import OpenAI

app = Flask(__name__)

# 環境変数
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)

THINKING_TIMEOUT_SEC = 10  # ← ここで閾値を調整できます（10秒）

def generate_reply(user_text: str) -> str:
    # ここはあなたの現在の生成ロジックでOK（例）
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたは思慮深いアシスタントです。"},
                {"role": "user", "content": user_text},
            ],
            temperature=0.6,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        tb = traceback.format_exc()
        print("=== OPENAI_ERROR ===")
        print(e)
        print(tb)
        app.logger.error(f"OPENAI_ERROR: {e}")
        # ここでは例外を投げ直して上位で処理
        raise

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        app.logger.error(f"Webhook handle error: {e}\n{traceback.format_exc()}")
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: MessageEvent):
    user_text = event.message.text
    reply_token = event.reply_token
    user_id = event.source.user_id  # 1:1想定。グループ対応するならsource.typeで分岐

    result = {"text": None, "error": None}
    done = threading.Event()

    def worker():
        try:
            result["text"] = generate_reply(user_text)
        except Exception as e:
            result["error"] = e
        finally:
            done.set()

    # OpenAI処理をバックグラウンドで開始
    threading.Thread(target=worker, daemon=True).start()

    # THINKING_TIMEOUT_SEC まで待つ
    if done.wait(timeout=THINKING_TIMEOUT_SEC):
        # 間に合った → そのままreply
        text = result["text"] if result["text"] else "ごめんなさい、内部エラーが出ました。もう一度お試しください。"
        line_bot_api.reply_message(reply_token, TextSendMessage(text=text))
    else:
        # 間に合わない → 先に短文でreplyして、完了後にpush
        line_bot_api.reply_message(reply_token, TextSendMessage(text="少しお待ちください…考えています。"))
        def pusher():
            done.wait()
            if result["text"] is None:
                app.logger.error(f"OPENAI_ERROR (late): {result['error']}\n{traceback.format_exc()}")
                final = "お待たせしました。内部エラーが発生しました。もう一度送ってください。"
            else:
                final = result["text"]
            try:
                line_bot_api.push_message(user_id, TextSendMessage(text=final))
            except Exception as e:
                app.logger.error(f"Push failed: {e}\n{traceback.format_exc()}")
        threading.Thread(target=pusher, daemon=True).start()
