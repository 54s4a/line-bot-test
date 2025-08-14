# -*- coding: utf-8 -*-
# ===== main.py (FastAPI + LINE) =====
# Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT

import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from asaoka_ai_layers import generate_reply  # ← ここだけを呼ぶ

# --- ENV ---
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
if not CHANNEL_SECRET or not CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN が未設定です。")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

app = FastAPI(title="AsaokaAI Webhook (FastAPI)")

@app.get("/")
async def root():
    return {"status": "ok", "app": "fastapi-webhook"}

@app.get("/version")
async def version():
    from importlib.util import find_spec
    return {
        "openai_installed": bool(find_spec("openai")),
        "openai_key_set": bool(os.environ.get("OPENAI_API_KEY")),
        "use_llm_env": os.environ.get("USE_LLM", "1"),
    }

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature.")
    return PlainTextResponse("OK")

@handler.add(MessageEvent, message=TextMessage)
def on_message(event: MessageEvent):
    user_text = (event.message.text or "").strip()
    try:
        result = generate_reply(user_text)   # ← レイヤー分離モジュールに委譲
        final_text = result.get("final") or "処理に失敗しました。もう一度お試しください。"
    except Exception as e:
        logging.exception("generate_reply error: %s", e)
        final_text = "処理中にエラーが発生しました。恐れ入りますが、もう一度お試しください。"

    # LINEの上限対策（安全に切り詰め）
    if len(final_text) > 4900:
        final_text = final_text[:4900] + "…（長文のため省略）"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=final_text))
