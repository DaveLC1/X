import yt_dlp
import os
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
    
BOT_TOKEN = "8565200793:AAFteufhny56VqgU3mKeYfkzNITFm4hQwuE"

# Store user links
user_links = {}

# STEP 1: HANDLE LINK
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.message.from_user.id

    if "twitter.com" not in url and "x.com" not in url:
        await update.message.reply_text("❌ Send a valid Twitter/X link.")
        return

    user_links[user_id] = url

    await update.message.reply_text("🔍 Fetching formats...")

    formats = []
    seen_qualities = set()

    ydl_opts = {"quiet": True}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        for f in info.get("formats", []):
            height = f.get("height")
            format_id = f.get("format_id")

            if not height or not format_id:
                continue

            # Avoid duplicate qualities (e.g multiple 720p)
            if height in seen_qualities:
                continue

            seen_qualities.add(height)

            filesize = f.get("filesize") or f.get("filesize_approx")

            if filesize:
                size_mb = round(filesize / (1024 * 1024), 2)
                text = f"{height}p - {size_mb}MB"
            else:
                text = f"{height}p"

            formats.append({
                "format_id": format_id,
                "text": text
            })

        if not formats:
            await update.message.reply_text("❌ No downloadable formats found)
            return

        # Sort qualities (highest first)
        formats = sorted(formats, key=lambda x: int(x["text"].split("p")[0]),>

        # Limit buttons
        formats = formats[:6]

        keyboard = [
            [InlineKeyboardButton(f["text"], callback_data=f["format_id"])]
            for f in formats
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🎬 Choose quality:", reply_markup=re>

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
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        with open(filename, "rb") as video:
            await query.message.reply_video(video)

        # Clean up file after sending
        os.remove(filename)

    except Exception as e:
        await query.message.reply_text(f"❌ Download failed:\n{e}")


# RUN BOT
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messag>
app.add_handler(CallbackQueryHandler(handle_button))

print("🚀 Bot is running...")
app.run_polling()
