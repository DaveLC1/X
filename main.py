import os
import re
import requests
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from flask import Flask

# 1. RENDER KEEP-ALIVE
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Deployment Active"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port, use_reloader=False)

BOT_TOKEN = "8875229976:AAFApchdQ-SI5-DvJYf_9E3ln4L8kPz8yHc"
user_data_store = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# 2. CUSTOM EXTRACTOR (NO LIBRARIES)
def extract_twitter_media(tweet_url):
    """
    Directly parses Twitter page data without yt-dlp or third-party APIs.
    Returns: ('video', list_of_quality_dicts) OR ('photo', list_of_image_urls)
    """
    # Convert x.com to fixvx/fxtwitter proxy for reliable open-graph metadata
    proxy_url = tweet_url.replace("x.com", "api.vxtwitter.com").replace("twitter.com", "api.vxtwitter.com")
    
    response = requests.get(proxy_url, headers=HEADERS, timeout=10)
    if response.status_code != 200:
        return None, None

    data = response.json()
    media_list = data.get("media_extended", [])

    if not media_list:
        return None, None

    # Check for Video
    first_media = media_list[0]
    if first_media.get("type") == "video" or first_media.get("type") == "gif":
        variants = first_media.get("variants", [])
        qualities = []

        for v in variants:
            video_url = v.get("url")
            if not video_url or ".m3u8" in video_url:
                continue

            # Extract resolution numbers from URL (e.g. 720x1280)
            res_match = re.search(r"/(\d+x\d+)/", video_url)
            height = "Video"
            if res_match:
                dimensions = res_match.group(1).split("x")
                height = f"{min(int(dimensions[0]), int(dimensions[1]))}p"

            # Estimate file size
            try:
                head = requests.head(video_url, headers=HEADERS, timeout=5)
                size_bytes = int(head.headers.get("Content-Length", 0))
                size_mb = f" ({round(size_bytes / (1024 * 1024), 1)}MB)" if size_bytes else ""
            except Exception:
                size_mb = ""

            qualities.append({
                "label": f"{height}{size_mb}",
                "url": video_url,
                "height_num": int(height.replace("p", "")) if height.endswith("p") else 0
            })

        # Sort lowest quality first (saving data)
        qualities = sorted(qualities, key=lambda x: x["height_num"])
        return "video", qualities

    # Check for Photos
    elif first_media.get("type") == "image":
        photo_urls = [m.get("url") for m in media_list if m.get("url")]
        return "photo", photo_urls

    return None, None


# STEP 1: RECEIVE LINK & SHOW OPTIONS
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.message.from_user.id

    if "twitter.com" not in url and "x.com" not in url:
        await update.message.reply_text("❌ Send a valid Twitter/X link.")
        return

    status_msg = await update.message.reply_text("🔍 Fetching media...")

    media_type, media_data = extract_twitter_media(url)

    if not media_data:
        await status_msg.edit_text("❌ Couldn't find media in this tweet (or tweet is private).")
        return

    # PHOTO TWEET
    if media_type == "photo":
        await status_msg.edit_text("🖼️ Downloading photo...")
        for img_url in media_data:
            img_bytes = requests.get(img_url, headers=HEADERS).content
            filename = f"{user_id}.jpg"
            with open(filename, "wb") as f:
                f.write(img_bytes)
            with open(filename, "rb") as p:
                await update.message.reply_photo(p)
            os.remove(filename)
        await status_msg.delete()
        return

    # VIDEO TWEET: Build Quality Selection Buttons
    if media_type == "video":
        user_data_store[user_id] = media_data

        keyboard = []
        for idx, q in enumerate(media_data):
            keyboard.append([InlineKeyboardButton(q["label"], callback_data=str(idx))])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_msg.edit_text("🎬 Select quality (Lowest data size top):", reply_markup=reply_markup)


# STEP 2: DOWNLOAD SELECTED QUALITY BUTTON CLICK
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_index = int(query.data)
    user_id = query.from_user.id
    user_qualities = user_data_store.get(user_id)

    if not user_qualities:
        await query.edit_message_text("⚠️ Session expired. Send link again.")
        return

    selected_video = user_qualities[selected_index]
    video_url = selected_video["url"]

    await query.edit_message_text(f"⬇️ Downloading {selected_video['label']}...")

    try:
        video_bytes = requests.get(video_url, headers=HEADERS).content
        filename = f"{user_id}.mp4"

        with open(filename, "wb") as f:
            f.write(video_bytes)

        with open(filename, "rb") as video_file:
            await query.message.reply_video(video_file)

        os.remove(filename)
        await query.message.delete()

    except Exception as e:
        await query.edit_message_text(f"❌ Download failed:\n{e}")


# RUN FLASK SERVER IN BACKGROUND
threading.Thread(target=run_web, daemon=True).start()

# RUN BOT
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(handle_button))

print("🚀 Custom Bot running cleanly...")
app.run_polling()
            
