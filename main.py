import os
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

web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Deployment Active"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port, use_reloader=False)

BOT_TOKEN = "8875229976:AAFApchdQ-SI5-DvJYf_9E3ln4L8kPz8yHc"
user_links = {}

COBALT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

# STEP 1: FETCH TWEET MEDIA & SHOW QUALITY OPTIONS
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.message.from_user.id

    if "twitter.com" not in url and "x.com" not in url:
        await update.message.reply_text("❌ Send a valid Twitter/X link.")
        return

    user_links[user_id] = url
    status_msg = await update.message.reply_text("🔍 Processing tweet...")

    try:
        # Request media from API
        payload = {"url": url}
        
        # We try primary public API instance
        api_url = "https://api.cobalt.tools/"
        res = requests.post(api_url, json=payload, headers=COBALT_HEADERS, timeout=10)

        # Fallback to secondary endpoint if first returns error format
        if res.status_code != 200:
            res = requests.post("https://co.wuk.sh/api/json", json=payload, headers=COBALT_HEADERS, timeout=10)

        res_data = res.json()
        status = res_data.get("status")

        # Handle Photo / Multi-Image Tweet
        if status == "picker":
            for item in res_data.get("picker", []):
                img_url = item.get("url")
                img_data = requests.get(img_url).content
                filename = f"{user_id}_photo.jpg"
                with open(filename, "wb") as f:
                    f.write(img_data)
                with open(filename, "rb") as photo:
                    await update.message.reply_photo(photo)
                os.remove(filename)
            await status_msg.delete()
            return

        # Handle Video (Present quality selection buttons to save data)
        if status in ["stream", "redirect", "tunnel", "picker-video"]:
            keyboard = [
                [
                    InlineKeyboardButton("360p (Data Saver)", callback_data="360"),
                    InlineKeyboardButton("480p (Medium)", callback_data="480"),
                ],
                [
                    InlineKeyboardButton("720p (HD)", callback_data="720"),
                    InlineKeyboardButton("1080p (Best Quality)", callback_data="1080"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await status_msg.edit_text("🎬 Select video quality to download:", reply_markup=reply_markup)
            return

        # If API returned error message directly
        error_text = res_data.get("text", "No media found in this tweet.")
        await status_msg.edit_text(f"❌ {error_text}")

    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to process link:\n{e}")


# STEP 2: DOWNLOAD SELECTED QUALITY
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    quality = query.data
    user_id = query.from_user.id
    url = user_links.get(user_id)

    if not url:
        await query.edit_message_text("⚠️ Session expired. Please send the link again.")
        return

    await query.edit_message_text(f"⬇️ Downloading {quality}p video...")

    try:
        payload = {
            "url": url,
            "videoQuality": quality,
        }
        
        # Primary endpoint
        res = requests.post("https://api.cobalt.tools/", json=payload, headers=COBALT_HEADERS, timeout=15)
        
        # Fallback endpoint
        if res.status_code != 200:
            res = requests.post("https://co.wuk.sh/api/json", json=payload, headers=COBALT_HEADERS, timeout=15)

        res_data = res.json()
        media_url = res_data.get("url")

        if not media_url:
            await query.edit_message_text("❌ Selected quality unavailable for this video.")
            return

        # Download media file
        file_response = requests.get(media_url, stream=True)
        filename = f"{user_id}.mp4"

        with open(filename, "wb") as f:
            for chunk in file_response.iter_content(chunk_size=8192):
                f.write(chunk)

        with open(filename, "rb") as video:
            await query.message.reply_video(video)

        os.remove(filename)
        await query.message.delete()

    except Exception as e:
        await query.edit_message_text(f"❌ Download failed:\n{e}")


# START FLASK WEB SERVER IN BACKGROUND
threading.Thread(target=run_web, daemon=True).start()

# RUN TELEGRAM BOT
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(handle_button))

print("🚀 Bot running...")
app.run_polling()
        
