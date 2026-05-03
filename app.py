"""
Main Flask application for the Exam Date Bot.
Handles webhook for Telegram updates, scheduling, and health checks.
"""

import logging
import json
import asyncio
import time
from datetime import datetime
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
import config
from scraper import NotificationScraper
from broadcaster import TelegramBroadcaster
from ai_processor import is_ai_available

# Configure logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize scraper and broadcaster
scraper = NotificationScraper(config.SEEN_NOTIFICATIONS_FILE)
channel_ids = config.get_channel_ids()
broadcaster = TelegramBroadcaster(config.TELEGRAM_BOT_TOKEN, channel_ids)

# Initialize APScheduler
scheduler = BackgroundScheduler()

# Global state
last_scrape_time = None
last_scrape_count = 0
bot_start_time = datetime.now().isoformat()


def send_telegram_reply(chat_id: int, text: str) -> None:
    """Send a reply to a Telegram chat using sync wrapper."""
    try:
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(bot.send_message(chat_id=chat_id, text=text))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Failed to send reply to {chat_id}: {e}")


def perform_scrape_and_broadcast() -> None:
    """Perform scraping and broadcasting of new notifications."""
    global last_scrape_time, last_scrape_count

    logger.info("Starting scheduled scrape and broadcast...")
    try:
        notifications = scraper.scrape_all()
        last_scrape_count = len(notifications)

        if notifications:
            logger.info(f"Found {len(notifications)} new notifications, broadcasting...")
            result = broadcaster.broadcast_notifications_sync(notifications)
            logger.info(f"Broadcast result: {result}")
        else:
            logger.info("No new notifications found")

        last_scrape_time = datetime.now().isoformat()
    except Exception as e:
        logger.error(f"Error during scrape and broadcast: {e}", exc_info=True)


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for Render."""
    ai_status = is_ai_available()
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "last_scrape": last_scrape_time,
        "channels": len(channel_ids),
        "ai_enabled": ai_status["any_available"],
        "ai_providers": {
            "groq": ai_status["groq"],
            "gemini": ai_status["gemini"],
        },
    }), 200


@app.route("/status", methods=["GET"])
def status():
    """Get bot status."""
    ai_status = is_ai_available()
    return jsonify({
        "status": "running",
        "started_at": bot_start_time,
        "timestamp": datetime.now().isoformat(),
        "last_scrape": last_scrape_time,
        "last_scrape_count": last_scrape_count,
        "channels": len(channel_ids),
        "scrape_interval_minutes": config.SCRAPE_INTERVAL_MINUTES,
        "webhook_url": config.WEBHOOK_URL or "Not configured",
        "ai_status": ai_status,
    }), 200


@app.route(config.WEBHOOK_PATH, methods=["POST"])
def webhook():
    """Webhook endpoint for Telegram updates."""
    try:
        data = request.get_json()
        logger.debug(f"Received webhook data: {json.dumps(data)}")

        if "message" in data:
            message = data["message"]
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "")

            if text == "/start":
                ai_status = is_ai_available()
                ai_text = "இயக்கத்தில்" if ai_status["any_available"] else "முடக்கத்தில்"
                reply = (
                    "🤖 தேர்வு நாள் அறிவிப்பு பாட் இயங்குகிறது!\n\n"
                    "இந்த பாட் TNPSC, SSC மற்றும் RRB தேர்வு நாள் "
                    "அறிவிப்புகளை தமிழில் ஒளிபரப்பும்.\n\n"
                    f"🤖 AI பகுப்பாய்வு: {ai_text}\n"
                    f"📢 சேனல்கள்: {len(channel_ids)}\n\n"
                    "நிலையை அறிய /status அனுப்பவும்."
                )
                send_telegram_reply(chat_id, reply)

            elif text == "/status":
                ai_status = is_ai_available()
                providers = []
                if ai_status["groq"]:
                    providers.append("Groq")
                if ai_status["gemini"]:
                    providers.append("Gemini")
                ai_text = ", ".join(providers) if providers else "முடக்கத்தில்"

                reply = (
                    f"📊 பாட் நிலை:\n\n"
                    f"✅ பாட் இயங்குகிறது\n"
                    f"📅 கடைசி ஸ்கேன்: {last_scrape_time or 'இன்னும் தொடங்கவில்லை'}\n"
                    f"📈 கடைசி ஸ்கேனில்: {last_scrape_count} அறிவிப்புகள்\n"
                    f"📢 சேனல்கள்: {len(channel_ids)}\n"
                    f"⏰ ஸ்கேன் இடைவெளி: {config.SCRAPE_INTERVAL_MINUTES} நிமிடங்கள்\n"
                    f"🤖 AI: {ai_text}"
                )
                send_telegram_reply(chat_id, reply)

        return jsonify({"ok": True}), 200
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/trigger-scrape", methods=["POST"])
def trigger_scrape():
    """Manually trigger scraping (for testing)."""
    try:
        perform_scrape_and_broadcast()
        return jsonify({
            "status": "success",
            "message": "Scrape triggered",
            "last_scrape": last_scrape_time,
            "notifications_found": last_scrape_count,
        }), 200
    except Exception as e:
        logger.error(f"Error triggering scrape: {e}", exc_info=True)
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/", methods=["GET"])
def index():
    """Root endpoint."""
    ai_status = is_ai_available()
    return jsonify({
        "name": "Exam Date Update Bot - தேர்வு நாள் அறிவிப்பு பாட்",
        "version": "2.0.0",
        "status": "running",
        "ai_enabled": ai_status["any_available"],
        "channels": len(channel_ids),
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "webhook": config.WEBHOOK_PATH,
            "trigger_scrape": "/trigger-scrape (POST)",
        },
    }), 200


def setup_webhook():
    """Set up Telegram webhook on startup."""
    if not config.WEBHOOK_URL:
        logger.warning(
            "RENDER_EXTERNAL_URL not set. Webhook not registered. "
            "Set RENDER_EXTERNAL_URL env var for webhook to work."
        )
        return

    try:
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(bot.set_webhook(url=config.WEBHOOK_URL))
            logger.info(f"Webhook set to {config.WEBHOOK_URL}: {result}")
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}", exc_info=True)


def init_scheduler():
    """Initialize the APScheduler for periodic scraping."""
    logger.info(
        f"Initializing scheduler with {config.SCRAPE_INTERVAL_MINUTES} minute interval"
    )

    scheduler.add_job(
        perform_scrape_and_broadcast,
        trigger=IntervalTrigger(minutes=config.SCRAPE_INTERVAL_MINUTES),
        id="scrape_job",
        name="Scrape and broadcast notifications",
        replace_existing=True,
    )
    scheduler.start()

    # Run initial scrape after a short delay
    logger.info("Initial scrape will run in 10 seconds...")
    scheduler.add_job(
        perform_scrape_and_broadcast,
        trigger="date",
        run_date=datetime.fromtimestamp(time.time() + 10),
        id="initial_scrape",
        name="Initial scrape on startup",
    )


# ── Initialize on module load (when gunicorn imports the app) ──
logger.info("=" * 50)
logger.info("Starting Exam Date Bot v2.0...")
logger.info(f"Bot Token: {'configured' if config.TELEGRAM_BOT_TOKEN else 'MISSING!'}")
logger.info(f"Broadcasting to {len(channel_ids)} channels")

ai_status = is_ai_available()
logger.info(f"AI Status - Groq: {ai_status['groq']}, Gemini: {ai_status['gemini']}")

if config.TELEGRAM_BOT_TOKEN:
    setup_webhook()
    init_scheduler()
else:
    logger.error("TELEGRAM_BOT_TOKEN not set! Bot cannot function.")

logger.info("=" * 50)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
