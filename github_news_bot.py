import html
import json
import logging
import os
import random
import time
from datetime import datetime

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from deep_translator import GoogleTranslator

# توکن و چت‌آیدی از GitHub Secrets خوانده می‌شوند.
TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
SEEN_FILE = "seen_news.json"

SITES = [
    {"name": "Tails' Channel", "url": "https://news.tailschannel.com/rss/"},
    {"name": "Sonic Stadium", "url": "https://www.sonicstadium.org/index.php?/rss/"},
    {"name": "SoaH City", "url": "https://soahcity.com/feed/"},
    {"name": "Sonic HQ", "url": "https://sonichq.net/feed/"},
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("github-sonic-news")


def create_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; SonicNewsBot/1.0)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = create_session()


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as file:
        json.dump(seen, file, ensure_ascii=False, indent=2)


def translate_to_persian(text):
    try:
        return GoogleTranslator(source="auto", target="fa").translate(text)
    except Exception as error:
        logger.warning("Translation failed: %s", error)
        return text


def get_feed_news(site):
    try:
        response = SESSION.get(site["url"], timeout=(10, 25))
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        news = []

        for entry in parsed.entries[:5]:
            title = str(entry.get("title", "")).strip()
            link = str(entry.get("link", "")).strip()
            if title and link:
                news.append({"title": title, "link": link})
        return news
    except Exception as error:
        logger.warning("Could not read %s: %s", site["name"], error)
        return []


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    response = SESSION.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        },
        timeout=(10, 25),
    )
    response.raise_for_status()
    return response.json().get("ok", False)


def main():
    seen = load_seen()
    new_news = []

    for index, site in enumerate(SITES):
        if index:
            time.sleep(random.uniform(2, 5))
        for article in get_feed_news(site):
            if article["link"] not in seen:
                new_news.append(article)

    sent = 0
    now = datetime.now().isoformat()
    for article in new_news:
        title = html.escape(translate_to_persian(article["title"]))
        link = html.escape(article["link"], quote=True)
        message = f"📰 <b>{title}</b>\n\n🔗 <a href=\"{link}\">مشاهده خبر</a>"
        try:
            if send_telegram(message):
                seen[article["link"]] = now
                sent += 1
        except Exception as error:
            logger.warning("Telegram send failed: %s", error)

    save_seen(seen)
    logger.info("Finished. Sent %s new items.", sent)


if __name__ == "__main__":
    main()
