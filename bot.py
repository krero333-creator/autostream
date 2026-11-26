import os
import time
import json
import urllib.request
import urllib.parse
import urllib.error

CLIENT_ID = os.environ["YT_CLIENT_ID"]
CLIENT_SECRET = os.environ["YT_CLIENT_SECRET"]
REFRESH_TOKENS = [
    t for t in [
        os.environ.get("YT_REFRESH_TOKEN", ""),
        os.environ.get("YT_REFRESH_TOKEN_2", ""),
    ] if t
]
PROMO_MESSAGE = os.environ.get("BOT_MESSAGE", "Всем привет! Подписывайтесь на канал!")
INTERVAL_SEC = int(os.environ.get("BOT_INTERVAL_SEC", "120"))


def get_access_token(refresh_token):
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
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
        "liveBroadcasts?part=snippet,status&mine=true&maxResults=10",
        token,
    )
    chats = []
    for item in res.get("items", []):
        lifecycle = item.get("status", {}).get("lifeCycleStatus", "")
        if lifecycle in ("live", "testing", "liveStarting"):
            chat_id = item.get("snippet", {}).get("liveChatId")
            if chat_id:
                chats.append(chat_id)
    return chats


def delete_message(token, message_id):
    try:
        yt_api("DELETE", f"liveChat/messages?id={urllib.parse.quote(message_id)}", token)
    except Exception as e:
        print(f"[WARN] Failed to delete {message_id}: {e}")


def ban_user(token, chat_id, channel_id):
    try:
        yt_api(
            "POST",
            "liveChat/bans?part=snippet",
            token,
            {
                "snippet": {
                    "liveChatId": chat_id,
                    "type": "permanent",
                    "bannedUserDetails": {"channelId": channel_id},
                }
            },
        )
    except Exception as e:
        print(f"[WARN] Failed to ban {channel_id}: {e}")


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
    tokens = {rt: (get_access_token(rt), time.time()) for rt in REFRESH_TOKENS}
    page_tokens = {}
    last_promo = 0

    while True:
        try:
            all_chats = []
            for rt in REFRESH_TOKENS:
                token, token_time = tokens[rt]
                if time.time() - token_time > 3000:
                    token = get_access_token(rt)
                    tokens[rt] = (token, time.time())

                chats = get_active_chats(token)
                for chat_id in chats:
                    all_chats.append((token, chat_id))
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
                            ch_id = author.get("channelId")
                            if ch_id:
                                ban_user(token, chat_id, ch_id)

        except Exception as e:
            print(f"[ERROR] {e}", flush=True)

        time.sleep(5)


if __name__ == "__main__":
    main()
