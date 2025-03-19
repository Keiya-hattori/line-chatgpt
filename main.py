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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """ ユーザーのメッセージを受け取り、ChatGPTの回答を送信 """
    try:
        user_message = event.message.text

        # ✅ 最新の OpenAI API に対応した書き方！
        response = openai.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": user_message}]
        )

        reply_text = response["choices"][0]["message"]["content"]  # ✅ 修正: 最新のアクセス方法

        # LINEに返信
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )

        print(f"✅ Sent reply: {reply_text}")

    except Exception as e:
        print(f"🚨 Error in handle_message: {e}")

    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)  # `debug=True` で詳細なログを出す
