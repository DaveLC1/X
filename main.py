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

# STEP 1: FETCH AVAILABLE QUALITIES VIA COBALT
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.message.from_user.id

    if "twitter.com" not in url and "x.com" not in url:
        await update.message.reply_text("❌ Send a valid Twitter/X link.")
        return

    user_links[user_id] = url
    status_msg = await update.message.reply_text("🔍 Fetching quality options...")

    try:
        # Check post via Cobalt API
        payload = {"url": url}
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        res = requests.post("https://api.cobalt.tools/api/json", json=payload, headers=headers).json()

        # Photos / Picker handling
        if res.get("status") == "picker":
            for item in res.get("picker", []):
                img_data = requests.get(item.get("url")).content
                filename = f"{user_id}_photo.jpg"
                with open(filename, "wb") as f:
                    f.write(img_data)
                with open(filename, "rb") as photo:
                    await update.message.reply_photo(photo)
                os.remove(filename)
            await status_msg.delete()
            return

        # Video post found: offer quality options to save data
        if res.get("status") in ["stream", "redirect", "success"]:
            keyboard = [
                [
                    InlineKeyboardButton("360p (Data Saver)", callback_data="360"),
                    InlineKeyboardButton("480p (Medium)", callback_data="480"),
                ],
                [
                    InlineKeyboardButton("720p (HD)", callback_data="720"),
                    InlineKeyboardButton("1080p (Best)", callback_data="1080"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await status_msg.edit_text("🎬 Choose video quality:", reply_markup=reply_markup)
            return
        
        await status_msg.edit_text("❌ Could not find media in this tweet.")

    except Exception as e:
        await status_msg.edit_text(f"❌ Error fetching post:\n{e}")


# STEP 2: DOWNLOAD SELECTED QUALITY
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    quality = query.data
    user_id = query.from_user.id
    url = user_links.get(user_id)

    if not url:
        await query.edit_message_text("⚠️ Session expired. Send link again.")
        return

    await query.edit_message_text(f"⬇️ Downloading {quality}p video...")

    try:
        payload = {
            "url": url,
            "videoQuality": quality,
        }
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        res = requests.post("https://api.cobalt.tools/api/json", json=payload, headers=headers).json()

        media_url = res.get("url")
        if not media_url:
            await query.edit_message_text("❌ Selected quality unavailable.")
            return

        file_response = requests.get(media_url)
        filename = f"{user_id}.mp4"

        with open(filename, "wb") as f:
            f.write(file_response.content)

        with open(filename, "rb") as video:
            await query.message.reply_video(video)

        os.remove(filename)
        await query.message.delete()

    except Exception as e:
        await query.edit_message_text(f"❌ Download failed:\n{e}")


# START FLASK SERVER IN BACKGROUND
threading.Thread(target=run_web, daemon=True).start()

# RUN BOT
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(handle_button))

print("🚀 Bot is running cleanly...")
app.run_polling()
        
