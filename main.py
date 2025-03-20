import os
import requests
import openai
from dotenv import load_dotenv
from flask import Flask, request
from linebot.v3.messaging import MessagingApi, Configuration, ApiClient
from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging.models import PushMessageRequest, TextMessage
from linebot.exceptions import LineBotApiError


# 環境変数の読み込み
load_dotenv()

# 🔹 環境変数を取得
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# OpenAI API 設定
openai.api_key = OPENAI_API_KEY

# LINE API 設定 (v3)
config = Configuration(access_token=LINE_ACCESS_TOKEN)
api_client = ApiClient(configuration=config)
messaging_api = MessagingApi(api_client=api_client)
handler = WebhookHandler(LINE_SECRET)

# Flaskアプリ
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    """ LINEのWebhookエンドポイント """
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except LineBotApiError:
        return "Invalid signature", 400

    return "OK", 200


from datetime import datetime, timezone, timedelta  # timezoneを追加

def search_youtube():
    """YouTube Data APIを使用して、特定のキーワードを含む最新動画を取得"""
    SEARCH_QUERY = "今だけ OR コスパ神 OR 穴場 OR 絶対行くべき OR お得"
    
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": SEARCH_QUERY,
        "type": "video",
        "maxResults": 50,  
        "order": "relevance",  
        "key": YOUTUBE_API_KEY
    }

    response = requests.get(url, params=params)
    # 🔹 デバッグ用の出力を追加
    print(f"🌍 YouTube API リクエストURL: {response.url}")  # ✅ APIのURLを確認
    print(f"📩 YouTube API ステータスコード: {response.status_code}")  # ✅ APIのレスポンスコード確認

    try:
        data = response.json()
        print(f"📊 YouTube API レスポンス（最初の3件）: {data.get('items', [])[:3]}")  # ✅ APIのレスポンスの一部を出力
    except requests.exceptions.JSONDecodeError:
        print("❌ APIレスポンスが正しく取得できませんでした！")
        return []

    video_results = []
    current_time = datetime.datetime.now(timezone.utc) # datetime.now() に変更

    for item in data.get("items", []):
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        published_at = item["snippet"]["publishedAt"]  # 公開日時を取得

    # 24時間以上経過かつ2週間以内の動画のみ対象
    published_time = datetime.datetime.strptime(published_at, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)

    time_diff = current_time - published_time

    if timedelta(days=1) <= time_diff <= timedelta(days=14):  # ✅ 24時間以上 & 2週間以内
        video_results.append((video_id, title, url, published_at))  # ここで追加
    else:
        print(f"⚠️ {title} は対象期間外のためスキップ（{published_at}）")

    return video_results

def get_video_comment_count(video_id):
    """動画のコメント数を取得する"""
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "statistics",
        "id": video_id,
        "key": YOUTUBE_API_KEY
    }
    
    response = requests.get(url, params=params).json()
    if "items" in response and len(response["items"]) > 0:
        return int(response["items"][0]["statistics"].get("commentCount", 0))
    return 0  # 取得できなかった場合は0を返す


### 🔹 YouTube動画のコメントを取得 ###
def get_youtube_comments(video_id):
    """YouTubeの動画コメントを取得する"""
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": 8,  # 10件取得
        "order": "relevance",
        "key": YOUTUBE_API_KEY
    }

    response = requests.get(url, params=params)
    results = response.json()

    comments = []
    if "items" in results:
        for item in results["items"]:
            comment_text = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            comments.append(comment_text)

    return comments


### 🔹 コメントが「有益」か判定 ###
def analyze_comment(comment_text):
    """ChatGPTを使ってコメントの有益性を判定"""
    prompt = f"""
   
        役割:
        あなたは、動画についたコメントを分析し、動画自体の有益性を判定する専門家です。

        状況:
        あなたは、最新のライフハックに関する動画のコメント欄を分析しています。

        目的:
        視聴者のコメントから、動画自体に本当に価値のある情報が含まれているかどうかを判定してください。

        出力形式:
        判定結果は以下の形式で出力してください。
        「判定: (有益✅/有益ではない)」
        「理由: (判定理由)」

        判断基準:
        以下の基準でコメントを分析し、判定してください。

        ✅ ポジティブなリアクション:

        「これは有益すぎる！」「神動画」「めちゃくちゃ役立った！」など、動画の内容に対して明確にポジティブな反応を示している場合は有益と判定する。
        短い感想でも、動画を高く評価していると読み取れる場合は有益と判断する。
        ✅ 驚き・感心のリアクション:

        「こんな情報無料でいいの？」「えーそうなんだ、すごい！」など、動画の情報に対して感心・驚いているコメントは有益と判定する。
        「なにこれ知らなかった、すごいな」のように、新しい情報を得た驚きが含まれている場合も有益とする。
        ✅ 動画の独自性を示すコメント:

        「この動画の情報、他のどこでも見たことない」「これ知ってる人少ないよね？」のように、動画の情報の価値を強調するコメントは有益と判定する。
        ✅ 後悔のリアクション:

        「もっと早く知りたかった」「今まで損してた！」など、動画の情報を事前に知りたかったという後悔を表しているコメントは有益とする。
        ✅ 隠しておきたいほどの有益性:

        「もうこの動画見たから消していいですよ笑」のように、「他の人に知られたくないほど価値がある」と解釈できるコメントは有益と判定する。
        ⛔ 有益ではないと判定するコメント:

        動画の内容に具体的に言及していない感想のみのコメント（例:「いいね」「面白かった」など）。
        ただの視聴報告や雑談コメント（例:「今見てるよ！」など）。
        動画とは関係のない話題のコメント。

        コメント: 「{comment_text}」


    """

    response = openai.chat.completions.create(  # ✅ `chat.completions.create` に修正
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )

    reply_text = response.choices[0].message.content  # ✅ 最新のOpenAI API形式
    is_useful = "✅" in reply_text  # 「✅」が含まれていたら有益
    reasoning = reply_text  # 理由をそのまま保持

    return is_useful, reasoning  # ✅ ここが2つの値を返す形になっているか確認

### 🔹 YouTube動画のコメントを取得 ###
def get_video_comments(video_id, max_results=10):
    """ 指定した動画のコメントを取得 """
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": max_results,
        "order": "relevance",  # できるだけ有益なコメントが上に来るようにする
        "key": YOUTUBE_API_KEY
    }

    response = requests.get(url, params=params)

    if response.status_code != 200:
        print(f"❌ コメント取得エラー: {response.status_code}")
        print(f"❌ エラーレスポンス: {response.text}")
        return []

    results = response.json()
    
    if "items" not in results:
        print("⚠️ 取得できるコメントがありません！")
        return []

    comments = []
    for item in results["items"]:
        comment_text = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
        comments.append(comment_text)

    print(f"✅ 取得したコメント: {comments}")
    return comments


### 🔹 有益な動画を探す ###
import datetime

def find_useful_video():
    """YouTubeの動画を検索し、有益な情報が含まれる動画を探す"""
    print("🔍 YouTubeで動画を検索中...")
    video_results = search_youtube()  # YouTubeから動画リストを取得
    if not video_results:
        print("⚠️ YouTubeの検索結果が空です！検索キーワードを変更してみてください。")
        return None, None, "YouTubeの検索結果が空でした", None

    checked_videos = []  # 確認した動画のリスト
    analyzed_comments = []  # 判定したコメントのリスト

    for video_id, title, url, published_at in video_results:
        # 公開日時をチェック（ISO8601形式をパース）
        published_time = datetime.datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
        time_diff = datetime.datetime.utcnow() - published_time

        if time_diff.total_seconds() < 86400:  # 24時間未満ならスキップ
            print(f"⚠️ {title} は公開から24時間未満のためスキップ")
            continue

        # コメント数をチェック
        comment_count = get_video_comment_count(video_id)
        if comment_count < 10:  # 10件未満の動画はスキップ
            print(f"⚠️ {title} はコメント数が少ないためスキップ ({comment_count}件)")
            continue

        print(f"🎥 チェック中: {title} ({url})")
        checked_videos.append(f'🎥 「{title}」 ({url})')

        comments = get_video_comments(video_id)
        if not comments:
            print(f"⚠️ {title} のコメントが取得できませんでした。")
            continue  # 次の動画へ

        for comment in comments:
            print(f"💬 コメント分析中: 「{comment}」")
            is_useful, reasoning = analyze_comment(comment)  # ChatGPTでコメントを分析
            analyzed_comments.append(f'- 「{comment}」\n  → ChatGPT判定: {"✅ 有益" if is_useful else "❌"}')

            if is_useful:  # ✅ 有益な情報が見つかった場合
                print(f"🎥 有益な動画を発見！: {title}\nURL: {url}")
                print(f"📝 ChatGPTの評価: {reasoning}")  
                print(f"💬 ユーザーのコメント: {comment}")  # ✅ 実際のコメントを表示
                return title, url, reasoning, comment  

    # 🔻 有益情報が見つからなかった場合 🔻
    summary = "📌 まとめ: 有益な情報と確信できるコメントが見つからなかったため、送信を見送りました。"
    debug_log = f"🎥 有益な情報は見つかりませんでした！\n🔍 チェックした動画:\n" + "\n".join(checked_videos) + \
                "\n\n📝 分析したコメント:\n" + "\n".join(analyzed_comments) + "\n\n" + summary
    print(debug_log)
    
    return None, None, debug_log, None  # 送信せずに終了

### 🔹 LINEに送信する ###
def send_article():
    """有益な情報をLINEに送信する"""
    title, url, reasoning, original_comment = find_useful_video()

    if url:
        message_text = f"🎥 お得情報発見！\n📌 {title}\n▶️ {url}\n\n📝 **ChatGPTの評価:** {reasoning}\n💬 **元コメント:** {original_comment}"
    else:
        message_text = "🎥 有益な情報は見つかりませんでした！"

    try:
        request_body = PushMessageRequest(to=LINE_USER_ID, messages=[TextMessage(text=message_text)])
        messaging_api.push_message(push_message_request=request_body)
        print(f"✅ LINEに送信完了:\n{message_text}")
    except LineBotApiError as e:
        print(f"🚨 LINE送信エラー: {e}")

import os

if __name__ == "__main__":
    if os.getenv("GITHUB_ACTIONS") == "true":
        send_article()  # GitHub Actions では send_article() のみ実行
    else:
        app.run(host="0.0.0.0", port=10000)  # ローカル開発時のみ Flask を起動
