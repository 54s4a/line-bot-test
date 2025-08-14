# -*- coding: utf-8 -*-
# ===== main.py (FastAPI + LINE Messaging API) =====
# Webhook入口: POST /callback
# Start Command (Render): uvicorn main:app --host 0.0.0.0 --port $PORT

import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from asaoka_ai_layers import generate_reply

# ---- Environment ----
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
if not CHANNEL_SECRET or not CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN が未設定です。Renderの環境変数に設定してください。")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ---- App ----
app = FastAPI(title="AsaokaAI Webhook (FastAPI)")

@app.get("/")
async def healthcheck():
    return {"status": "ok"}

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    try:
        handler.handle(body_text, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature.")

    return PlainTextResponse("OK")

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: MessageEvent):
    user_text = event.message.text.strip()
    try:
        result = generate_reply(user_text)  # レイヤー分離の最終文を生成
        final_text = result["final"]
    except Exception as e:
        logging.exception("generate_reply でエラー: %s", e)
        final_text = "処理中にエラーが発生しました。恐れ入りますが、もう一度お試しください。"

    # ★必ず1回だけ返信
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=final_text))
