"""
Broadcaster module for sending exam date announcements to Telegram channels.
Clean Tamil announcements with 0.5s delay between messages.

NO AI credit lines.
NO random external links.
ONLY official government links + employmenttamil.in/shop
"""

import logging
import asyncio
from typing import List, Dict, Any
from telegram import Bot
from telegram.error import TelegramError, RetryAfter

logger = logging.getLogger(__name__)

# Rate limiting: 0.5 second delay between each message
BROADCAST_DELAY = 0.5

# Tamil labels for date types
DATE_TYPE_TAMIL = {
    "exam_date": "📝 தேர்வு நாள்",
    "hall_ticket": "🎫 ஹால் டிக்கெட் வெளியீடு",
    "hall_ticket_date": "🎫 ஹால் டிக்கெட் வெளியீடு",
    "application_start": "📋 விண்ணப்பம் தொடக்க நாள்",
    "application_start_date": "📋 விண்ணப்பம் தொடக்க நாள்",
    "application_end": "⏰ விண்ணப்பம் கடைசி நாள்",
    "application_end_date": "⏰ விண்ணப்பம் கடைசி நாள்",
    "date_extension": "📅 நாள் நீட்டிப்பு",
    "postponed": "⚠️ தேர்வு ஒத்திவைப்பு",
    "postponed_to": "⚠️ ஒத்திவைக்கப்பட்ட புதிய நாள்",
    "result_date": "📊 முடிவு வெளியீடு",
    "notification_date": "📢 அறிவிப்பு நாள்",
    "extended_date": "📅 நீட்டிக்கப்பட்ட நாள்",
    "new_date": "🔄 புதிய நாள்",
}

# Source name mapping to Tamil
SOURCE_TAMIL = {
    "TNPSC": "TNPSC (தமிழ்நாடு அரசுப் பணியாளர் தேர்வாணையம்)",
    "SSC": "SSC (பணியாளர் தேர்வு ஆணையம்)",
    "RRB Chennai": "RRB (இரயில்வே ஆட்சேர்ப்பு வாரியம்)",
}


class TelegramBroadcaster:
    """Broadcasts exam date notifications to Telegram channels."""

    def __init__(self, bot_token: str, channel_ids: List[str]):
        self.bot_token = bot_token
        self.channel_ids = channel_ids
        logger.info(f"Broadcaster initialized with {len(channel_ids)} channels")

    def _format_tamil_announcement(self, notification: Dict[str, Any]) -> str:
        """
        Format notification as a clean Tamil announcement.
        Simple, clear, with only dates and official links.
        NO AI credit. NO unnecessary text.
        """
        source = notification.get("source", "அறிவிப்பு")
        title = notification.get("title", "")
        url = notification.get("url", "")
        date_details = notification.get("date_details", {})

        source_tamil = SOURCE_TAMIL.get(source, source)

        # Use AI Tamil title if available
        if date_details.get("ai_processed") and date_details.get("title_tamil"):
            display_title = date_details["title_tamil"]
        else:
            display_title = title[:200]

        # Post name
        post_name = date_details.get("post_name", "")

        # Build announcement
        msg = f"📢 {source_tamil} அறிவிப்பு\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

        # Title
        msg += f"📌 {display_title}\n"

        # Post name if available
        if post_name:
            msg += f"🏷️ பதவி: {post_name}\n"

        # Date details section
        specific_dates = date_details.get("specific_dates", {})
        if specific_dates:
            msg += "\n📅 முக்கிய நாட்கள்:\n\n"
            for key, date_val in specific_dates.items():
                if date_val and str(date_val).lower() not in ("null", "none", ""):
                    label = DATE_TYPE_TAMIL.get(key, key)
                    msg += f"  ▪️ {label}: {date_val}\n"

        # Extension/Postponement alert
        if date_details.get("is_extension"):
            msg += "\n⚡ நாள் நீட்டிக்கப்பட்டுள்ளது!\n"
        if date_details.get("is_postponed"):
            msg += "\n⚡ தேர்வு ஒத்திவைக்கப்பட்டுள்ளது!\n"

        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"

        # Official link (only government URLs)
        if url and (".gov.in" in url or ".nic.in" in url):
            msg += f'\n🔗 <a href="{url}">அதிகாரப்பூர்வ அறிவிப்பு</a>\n'

        # Shop link — always included
        msg += '\n🛒 <a href="https://employmenttamil.in/shop/">விற்பனை நிலையம்</a>'

        return msg

    async def broadcast_notification(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Broadcast a single notification to all channels.
        0.5 second delay between each message.
        """
        bot = Bot(token=self.bot_token)
        message = self._format_tamil_announcement(notification)
        results = {"success": [], "failed": []}

        logger.info(f"Broadcasting to {len(self.channel_ids)} channels...")

        for i, channel_id in enumerate(self.channel_ids):
            try:
                await bot.send_message(
                    chat_id=channel_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                results["success"].append(channel_id)
                logger.debug(f"[{i+1}/{len(self.channel_ids)}] Sent to {channel_id}")

                # 0.5s delay between each message
                await asyncio.sleep(BROADCAST_DELAY)

            except RetryAfter as e:
                wait_time = e.retry_after
                logger.warning(f"Rate limited for {channel_id}. Waiting {wait_time}s...")
                await asyncio.sleep(wait_time + 1)

                # Retry once
                try:
                    await bot.send_message(
                        chat_id=channel_id,
                        text=message,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    results["success"].append(channel_id)
                except Exception as retry_err:
                    results["failed"].append({
                        "channel": channel_id,
                        "error": str(retry_err)
                    })

            except TelegramError as e:
                error_msg = str(e)
                results["failed"].append({"channel": channel_id, "error": error_msg})
                logger.warning(f"Failed for {channel_id}: {error_msg}")
                await asyncio.sleep(BROADCAST_DELAY)

            except Exception as e:
                results["failed"].append({"channel": channel_id, "error": str(e)})
                logger.error(f"Unexpected error for {channel_id}: {e}")
                await asyncio.sleep(BROADCAST_DELAY)

        success_count = len(results["success"])
        fail_count = len(results["failed"])
        logger.info(f"Broadcast done: {success_count} success, {fail_count} failed")
        return results

    async def broadcast_notifications(
        self, notifications: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Broadcast multiple notifications to all channels."""
        if not notifications:
            logger.info("No notifications to broadcast")
            return {"total": 0, "results": []}

        logger.info(f"Broadcasting {len(notifications)} notifications...")
        all_results = []

        for idx, notification in enumerate(notifications):
            logger.info(
                f"[{idx+1}/{len(notifications)}] "
                f"{notification.get('source', '')} - "
                f"{notification.get('title', '')[:50]}"
            )
            result = await self.broadcast_notification(notification)
            all_results.append({
                "notification": notification.get("title", "")[:100],
                "source": notification.get("source", ""),
                "result": result,
            })

            # 1s delay between different notifications
            if idx < len(notifications) - 1:
                await asyncio.sleep(1.0)

        total_success = sum(len(r["result"]["success"]) for r in all_results)
        total_failed = sum(len(r["result"]["failed"]) for r in all_results)
        logger.info(f"All done: {total_success} sent, {total_failed} failed")

        return {"total": len(notifications), "results": all_results}

    def broadcast_notifications_sync(
        self, notifications: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Synchronous wrapper for APScheduler background thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.broadcast_notifications(notifications)
            )
        finally:
            loop.close()
