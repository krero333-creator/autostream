import os
import time
import json
import urllib.request
import urllib.parse
import urllib.error

CLIENT_ID = os.environ["YT_CLIENT_ID"]
CLIENT_SECRET = os.environ["YT_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["YT_REFRESH_TOKEN"]
PROMO_MESSAGE = os.environ.get("BOT_MESSAGE", "Всем привет! Подписывайтесь на канал!")
INTERVAL_SEC = int(os.environ.get("BOT_INTERVAL_SEC", "120"))


def get_access_token():
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())["access_token"]


def yt_api(method, path, token, body=None):
    url = f"https://www.googleapis.com/youtube/v3/{path}"
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def get_active_chats(token):
    res = yt_api(
        "GET",
        "liveBroadcasts?part=snippet&broadcastStatus=active&broadcastType=all",
        token,
    )
    chats = []
    for item in res.get("items", []):
        chat_id = item.get("snippet", {}).get("liveChatId")
        if chat_id:
            chats.append(chat_id)
    return chats


def delete_message(token, message_id):
    try:
        yt_api("DELETE", f"liveChat/messages?id={urllib.parse.quote(message_id)}", token)
    except Exception as e:
        print(f"[WARN] Failed to delete {message_id}: {e}")


def send_message(token, chat_id, text):
    try:
        yt_api(
            "POST",
            "liveChat/messages?part=snippet",
            token,
            {
                "snippet": {
                    "liveChatId": chat_id,
                    "type": "textMessageEvent",
                    "textMessageDetails": {"messageText": text},
                }
            },
        )
        print(f"[BOT] Sent message to {chat_id}")
    except Exception as e:
        print(f"[WARN] Failed to send message to {chat_id}: {e}")


def main():
    token = get_access_token()
    token_time = time.time()
    page_tokens = {}
    last_promo = 0

    while True:
        try:
            if time.time() - token_time > 3000:
                token = get_access_token()
                token_time = time.time()

            chats = get_active_chats(token)
            for chat_id in chats:
                pt = page_tokens.get(chat_id, "")
                pt_param = f"&pageToken={urllib.parse.quote(pt)}" if pt else ""
                res = yt_api(
                    "GET",
                    f"liveChat/messages?liveChatId={urllib.parse.quote(chat_id)}&part=snippet,authorDetails{pt_param}",
                    token,
                )
                page_tokens[chat_id] = res.get("nextPageToken", "")

                for msg in res.get("items", []):
                    author = msg.get("authorDetails", {})
                    if not author.get("isChatOwner", False):
                        delete_message(token, msg["id"])

            if time.time() - last_promo >= INTERVAL_SEC and chats:
                for chat_id in chats:
                    send_message(token, chat_id, PROMO_MESSAGE)
                last_promo = time.time()

        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(5)


if __name__ == "__main__":
    main()
