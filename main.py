import yt_dlp
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

# BYPASS TWITTER/X BLOCKS & SCRAPE FORMATS
BASE_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "check_formats": False,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "http_headers": {
        "Referer": "https://x.com/",
        "Accept": "*/*",
    },
    "extractor_args": {
        "twitter": {
            "api": "syndication",
        }
    }
}

# STEP 1: HANDLE LINK & SHOW QUALITY OPTIONS
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.message.from_user.id

    if "twitter.com" not in url and "x.com" not in url:
        await update.message.reply_text("❌ Send a valid Twitter/X link.")
        return

    user_links[user_id] = url
    status_msg = await update.message.reply_text("🔍 Fetching quality formats...")

    try:
        # Try fetching formats via yt-dlp first
        with yt_dlp.YoutubeDL(BASE_YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

        if "entries" in info:
            info = info["entries"][0]

        formats_list = info.get("formats", [])
        formats = []
        seen_qualities = set()

        for f in formats_list:
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
            size_mb = f" ({round(filesize / (1024 * 1024), 1)}MB)" if filesize else ""

            formats.append({
                "format_id": format_id,
                "text": f"{label}{size_mb}"
            })

        # If formats found, display buttons (lowest to highest quality)
        if formats:
            formats = sorted(
                formats,
                key=lambda x: int(x["text"].split("p")[0]) if x["text"].split("p")[0].isdigit() else 0
            )[:6]

            keyboard = [
                [InlineKeyboardButton(f["text"], callback_data=f["format_id"])]
                for f in formats
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await status_msg.edit_text("🎬 Choose video quality:", reply_markup=reply_markup)
            return

    except Exception:
        pass  # If yt-dlp fails (e.g., photo post or full block), fallback to direct Cobalt download below

    # FALLBACK FOR PHOTOS / BLOCKED POSTS
    try:
        res = requests.post(
            "https://api.cobalt.tools/api/json",
            json={"url": url},
            headers={"Accept": "application/json", "Content-Type": "application/json"}
        ).json()

        if res.get("status") in ["stream", "redirect"]:
            file_response = requests.get(res.get("url"))
            content_type = file_response.headers.get("Content-Type", "")
            ext = ".mp4" if "video" in content_type else ".jpg"
            filename = f"{user_id}{ext}"

            with open(filename, "wb") as f:
                f.write(file_response.content)

            with open(filename, "rb") as media_file:
                if ext == ".mp4":
                    await update.message.reply_video(media_file)
                else:
                    await update.message.reply_photo(media_file)

            os.remove(filename)
            await status_msg.delete()
            return

        elif res.get("status") == "picker":
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

    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to fetch media:\n{e}")


# STEP 2: HANDLE BUTTON CLICK (DOWNLOAD SPECIFIC FORMAT)
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    format_id = query.data
    user_id = query.from_user.id
    url = user_links.get(user_id)

    if not url:
        await query.edit_message_text("⚠️ Session expired. Send link again.")
        return

    await query.edit_message_text("⬇️ Downloading chosen quality...")

    filename = f"{user_id}.mp4"

    ydl_opts = {
        **BASE_YDL_OPTS,
        "format": format_id,
        "outtmpl": filename,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        with open(filename, "rb") as video:
            await query.message.reply_video(video)

        os.remove(filename)

    except Exception as e:
        await query.message.reply_text(f"❌ Download failed:\n{e}")


# START FLASK SERVER IN BACKGROUND
threading.Thread(target=run_web, daemon=True).start()

# RUN BOT
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(handle_button))

print("🚀 Bot is running...")
app.run_polling()
