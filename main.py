# main.py
import os
import time
import threading
import traceback
from collections import deque

from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError

from openai import OpenAI

# ---------------------------
# 基本設定
# ---------------------------
app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------------------
# 応答時間の自己調整メトリクス
# ---------------------------
metrics = {"samples": deque(maxlen=200), "ema": None, "n": 0}

def record_elapsed(sec: float):
    """OpenAI呼び出しの所要時間を記録"""
    metrics["samples"].append(sec)
    metrics["n"] += 1
    alpha = 0.2  # 平滑化係数（大きいほど最新を重視）
    metrics["ema"] = sec if metrics["ema"] is None else (1 - alpha) * metrics["ema"] + alpha * sec
    app.logger.info(f"openai_elapsed={sec:.2f}s ema={metrics['ema']:.2f}s n={metrics['n']}")

def current_timeout() -> float:
    """待機タイムアウト（返信トークン失効を避けるための閾値）を動的に算出"""
    if metrics["n"] < 30 or metrics["ema"] is None:
        return 10.0  # サンプル不足時はまず10秒固定で運用
    t = metrics["ema"] * 1.3  # 余裕を持たせる
    # 下限/上限でクリップ（必要に応じて調整可）
    return max(8.0, min(18.0, t))

# ---------------------------
# 生成系
# ---------------------------
def generate_reply(user_text: str) -> str:
    """OpenAIに問い合わせて返信文を生成"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたは思慮深く、簡潔で誠実な日本語で回答します。"},
                {"role": "user", "content": user_text},
            ],
            temperature=0.6,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        # ここでログを厚く出す
        tb = traceback.format_exc()
        print("=== OPENAI_ERROR ===")
        print(e)
        print(tb)
        app.logger.error(f"OPENAI_ERROR: {e}\n{tb}")
        # 上位で制御するため例外をそのまま投げる
        raise

# ---------------------------
# ルーティング
# ---------------------------
@app.get("/")
def health():
    """ヘルスチェック用（RenderのHEAD/GET 404を抑止）"""
    return "ok", 200

@app.post("/callback")
def callback():
    """LINE Webhook受入口"""
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature")
        abort(400)
    except Exception as e:
        app.logger.error(f"Webhook handle error: {e}\n{traceback.format_exc()}")
        abort(400)

    return "OK"

# ---------------------------
# イベントハンドラ
# ---------------------------
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: MessageEvent):
    user_text = event.message.text
    reply_token = event.reply_token

    # push の宛先（1:1／グループ／ルームいずれにも対応）
    source_type = event.source.type
    if source_type == "user":
        push_to = event.source.user_id
    elif source_type == "group":
        push_to = event.source.group_id
    elif source_type == "room":
        push_to = event.source.room_id
    else:
        push_to = None  # 念のため

    result = {"text": None, "error": None}
    done = threading.Event()

    def worker():
        """重い生成処理を別スレッドで実行"""
        start = time.time()
        try:
            text = generate_reply(user_text)
            result["text"] = text
        except Exception as e:
            result["error"] = e
        finally:
            # 所要時間の記録（エラーの場合でも計測は残す）
            elapsed = time.time() - start
            try:
                record_elapsed(elapsed)
            except Exception:
                pass
            done.set()

    threading.Thread(target=worker, daemon=True).start()

    wait_sec = current_timeout()
    if done.wait(timeout=wait_sec):
        # 所定時間内に完了 → そのまま reply（reply_token は1回限り）
        text = result["text"] if result["text"] else "申し訳ありません。内部でエラーが発生しました。もう一度お試しください。"
        try:
            line_bot_api.reply_message(reply_token, TextSendMessage(text=text))
        except Exception as e:
            app.logger.error(f"reply_message failed: {e}\n{traceback.format_exc()}")
    else:
        # 間に合わない → 先に短文で reply、完了後に push で本返信
        try:
            line_bot_api.reply_message(reply_token, TextSendMessage(text="少しお待ちください…考えています。"))
        except Exception as e:
            app.logger.error(f"reply (placeholder) failed: {e}\n{traceback.format_exc()}")

        def pusher():
            done.wait()
            if result["text"] is None:
                final = "お待たせしました。内部エラーが発生しました。もう一度送ってください。"
            else:
                final = result["text"]

            if push_to:
                try:
                    line_bot_api.push_message(push_to, TextSendMessage(text=final))
                except Exception as e:
                    app.logger.error(f"push_message failed: {e}\n{traceback.format_exc()}")
            else:
                app.logger.error("push target not found; message dropped.")

        threading.Thread(target=pusher, daemon=True).start()

# ---------------------------
# ローカル実行用（Renderでは不要）
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
