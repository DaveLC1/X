import yt_dlp
import os
import requests
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

# STEP 1: HANDLE LINK
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.message.from_user.id

    if "twitter.com" not in url and "x.com" not in url:
        await update.message.reply_text("❌ Send a valid Twitter/X link.")
        return

    user_links[user_id] = url

    await update.message.reply_text("🔍 Fetching media...")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "http_headers": {
            "Referer": "https://x.com/",
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # Check for image post
        images = [
            f.get("url") for f in info.get("formats", [])
            if f.get("ext") in ["jpg", "jpeg", "png", "webp"] or f.get("vcodec") == "none" and f.get("acodec") == "none"
        ]
        
        # Fallback check for single thumbnail/photo entry
        if not images and info.get("ext") in ["jpg", "jpeg", "png", "webp"]:
            images = [info.get("url")]

        if images:
            # Direct photo download
            img_url = images[0]
            img_data = requests.get(img_url).content
            filename = f"{user_id}.jpg"
            with open(filename, "wb") as f:
                f.write(img_data)
            with open(filename, "rb") as photo:
                await update.message.reply_photo(photo)
            os.remove(filename)
            return

        # Handle video formats
        formats = []
        seen_qualities = set()

        for f in info.get("formats", []):
            if f.get("vcodec") == "none":
                continue

            height = f.get("height")
            format_id = f.get("format_id")

            if not format_id:
                continue

            label = f"{height}p" if height else format_id

            if height and height in seen_qualities:
                continue
            if height:
                seen_qualities.add(height)

            filesize = f.get("filesize") or f.get("filesize_approx")
            size_mb = f" - {round(filesize / (1024 * 1024), 2)}MB" if filesize else ""

            formats.append({
                "format_id": format_id,
                "text": f"{label}{size_mb}"
            })

        if not formats:
            await update.message.reply_text("❌ No downloadable media found")
            return

        formats = sorted(
            formats,
            key=lambda x: int(x["text"].split("p")[0]) if x["text"].split("p")[0].isdigit() else 0,
            reverse=True
        )[:6]

        keyboard = [
            [InlineKeyboardButton(f["text"], callback_data=f["format_id"])]
            for f in formats
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🎬 Choose quality:", reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching formats:\n{e}")


# STEP 2: HANDLE BUTTON CLICK
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    format_id = query.data
    user_id = query.from_user.id
    url = user_links.get(user_id)

    if not url:
        await query.edit_message_text("⚠️ Session expired. Send link again.")
        return

    await query.edit_message_text("⬇️ Downloading...")

    filename = f"{user_id}.mp4"

    ydl_opts = {
        "format": format_id,
        "outtmpl": filename,
        "quiet": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "http_headers": {
            "Referer": "https://x.com/",
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        with open(filename, "rb") as video:
            await query.message.reply_video(video)

        os.remove(filename)

    except Exception as e:
        await query.message.reply_text(f"❌ Download failed:\n{e}")


# RUN BOT
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(handle_button))

print("🚀 Bot is running...")
app.run_polling()
