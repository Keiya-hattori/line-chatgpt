from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import openai
import os

# 環境変数を取得
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Flaskアプリ
app = Flask(__name__)

# 追加したコード（トップページ用）
@app.route("/", methods=["GET"])
def home():
    return "LINE Chatbot is running!", 200


# LINE Botのセットアップ
line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# OpenAI APIキー設定
openai.api_key = OPENAI_API_KEY

@app.route("/webhook", methods=["POST"])
def webhook():
    """ LINEのWebhookエンドポイント """
    signature = request.headers.get("X-Line-Signature")  # `.get()` でエラーハンドリング
    body = request.get_data(as_text=True)

    # デバッグ用ログ（Renderの「Logs」で確認できる）
    print("📩 Webhook received!")
    print("Headers:", request.headers)
    print("Body:", body)

    if not signature:
        print("🚨 Error: X-Line-Signature not found in headers")
        return jsonify({"error": "X-Line-Signature header is missing"}), 400  # 400 Bad Request

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("🚨 Error: Invalid signature")
        return jsonify({"error": "Invalid signature"}), 400

    return jsonify({"status": "ok"}), 200

import openai
import time

client = openai.OpenAI()  # ✅ 最新APIの書き方

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """ ユーザーのメッセージを受け取り、ChatGPTの回答を送信 """
    try:
        user_message = event.message.text  # ユーザーのメッセージ

        # 使用するモデルを最初は gpt-4o に設定
        model = "gpt-4o"

        try:
            # ✅ `client.chat.completions.create()` を使う
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": user_message}]
            )

        except openai.RateLimitError:
            print("Rate limit or quota exceeded for gpt-4o, switching to gpt-4o-mini...")
            # gpt-4o で制限エラーが発生した場合、gpt-4o-mini に切り替え
            model = "gpt-4o-mini"
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": user_message}]
            )

        reply_text = response.choices[0].message.content  # ✅ 修正済みのレスポンス取得

        # LINEに返信
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )

        print(f"✅ Sent reply: {reply_text}")

    except openai.RateLimitError as e:
        print(f"🚨 API Rate Limit exceeded: {e}")
    except openai.APIError as e:
        print(f"🚨 API Error: {e}")
    except Exception as e:
        print(f"🚨 Error in handle_message: {e}")
        
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)  # `debug=True` で詳細なログを出す
