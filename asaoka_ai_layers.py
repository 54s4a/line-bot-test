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

# ---- Environment ----
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
if not CHANNEL_SECRET or not CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN が未設定です。Renderの環境変数に設定してください。")

# （任意）OpenAIキーは asaoka_ai_layers.py 側で参照します
# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# ---- LINE SDK ----
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ---- App ----
app = FastAPI(title="AsaokaAI Webhook (FastAPI)")

@app.get("/")
async def healthcheck():
    return {"status": "ok", "app": "fastapi-webhook"}

@app.post("/callback")
async def callback(request: Request):
    # LINE署名検証
    signature = request.headers.get("X-Line-Signature", "")
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")
    try:
        handler.handle(body_text, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature.")
    return PlainTextResponse("OK")

# ---- Event Handler ----
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: MessageEvent):
    user_text = (event.message.text or "").strip()

    # 1) 思想レイヤー分離で加工（核/中立/実務/まとめ/次の一手 → 統合）
    try:
        result = generate_reply(user_text)
        final_text = result.get("final") or "処理に失敗しました。もう一度お試しください。"
    except Exception as e:
        logging.exception("generate_reply error: %s", e)
        final_text = "処理中にエラーが発生しました。恐れ入りますが、もう一度お試しください。"

    # 2) LINEの文字数上限ガード（安全側で切り詰め）
    #   LINEのテキストは最大5000文字。超える場合は末尾に省略記号を付与。
    MAX_LEN = 4900
    if len(final_text) > MAX_LEN:
        final_text = final_text[:MAX_LEN] + "…（長文のため省略）"

    # 3) 返信（必ず1回）
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=final_text)
        )
    except Exception as e:
        logging.exception("reply_message error: %s", e)
