"""
Broadcaster module for sending exam date announcements to Telegram channels.
Handles multi-channel broadcasting with rate limiting and message formatting in Tamil.

Rate Limiting Strategy:
- 0.5 second delay between each message to avoid Telegram API rate limits
- Automatic retry on RetryAfter errors with the specified wait time
- Graceful handling of blocked/unavailable channels
"""

import logging
import asyncio
from typing import List, Dict, Any
from telegram import Bot
from telegram.error import TelegramError, RetryAfter

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# RATE LIMITING: 0.5 second delay between each message
# Telegram allows ~30 messages/second to different chats,
# but being conservative to avoid 429 errors with 96 channels
# ──────────────────────────────────────────────
BROADCAST_DELAY = 0.5

# Tamil labels for date types used in announcements
DATE_TYPE_TAMIL = {
    "exam_date": "📝 தேர்வு நாள்",
    "hall_ticket": "🎫 ஹால் டிக்கெட் வெளியீடு",
    "hall_ticket_date": "🎫 ஹால் டிக்கெட் வெளியீடு",
    "application_start": "📋 விண்ணப்பம் தொடக்க நாள்",
    "application_start_date": "📋 விண்ணப்பம் தொடக்க நாள்",
    "application_end": "⏰ விண்ணப்பம் கடைசி நாள்",
    "application_end_date": "⏰ விண்ணப்பம் கடைசி நாள்",
    "date_extension": "📅 நாள் நீட்டிப்பு",
    "postponed": "⚠️ தேர்வு ஒத்திவைப்பு / தாமதம்",
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
        logger.info(f"Rate limit delay: {BROADCAST_DELAY}s between messages")

    def _format_date_details_tamil(self, date_details: Dict[str, Any]) -> str:
        """Format extracted date details into Tamil text."""
        if not date_details:
            return ""

        lines = []
        ai_processed = date_details.get("ai_processed", False)

        # ── AI-processed content (richer, with Tamil translation) ──
        if ai_processed:
            # Post name from AI
            post_name = date_details.get("post_name", "")
            if post_name:
                lines.append(f"\n🏷️ பதவி: {post_name}")

            # AI Tamil summary
            summary = date_details.get("summary_tamil", "")
            if summary:
                lines.append(f"\n📄 {summary}")

            # Date type header
            date_type = date_details.get("date_type", "notification_date")
            type_label = DATE_TYPE_TAMIL.get(date_type, "📢 அறிவிப்பு")
            lines.append(f"\n{type_label}")

        else:
            # Basic date type header (regex fallback)
            date_type = date_details.get("date_type", "notification_date")
            type_label = DATE_TYPE_TAMIL.get(date_type, "📢 அறிவிப்பு")
            lines.append(f"\n{type_label}")

        # ── Specific dates section ──
        specific_dates = date_details.get("specific_dates", {})
        if specific_dates:
            lines.append("")
            for key, date_val in specific_dates.items():
                if date_val and str(date_val).lower() not in ("null", "none", ""):
                    label = DATE_TYPE_TAMIL.get(key, key)
                    lines.append(f"  ▪️ {label}: {date_val}")

        # ── Extension / Postponement alerts ──
        if date_details.get("is_extension"):
            lines.append("\n⚡ நாள் நீட்டிக்கப்பட்டுள்ளது!")
        if date_details.get("is_postponed"):
            lines.append("\n⚡ தேர்வு ஒத்திவைக்கப்பட்டுள்ளது / தாமதமாகியுள்ளது!")

        # ── Important note from AI ──
        if ai_processed:
            note = date_details.get("important_note_tamil", "")
            if note:
                lines.append(f"\n💡 குறிப்பு: {note}")

        # ── Fallback: list dates if no specific categorization ──
        if not specific_dates and date_details.get("dates_found"):
            lines.append("")
            lines.append("  📅 முக்கிய நாட்கள்:")
            for date_val in date_details["dates_found"][:5]:
                lines.append(f"    • {date_val}")

        return "\n".join(lines)

    def _format_tamil_announcement(self, notification: Dict[str, Any]) -> str:
        """
        Format notification as Tamil announcement with date details.
        Uses AI-translated Tamil title/summary when available.
        """
        source = notification.get("source", "அறிவிப்பு")
        title = notification.get("title", "")
        url = notification.get("url", "")
        date_details = notification.get("date_details", {})

        source_tamil = SOURCE_TAMIL.get(source, source)
        ai_processed = date_details.get("ai_processed", False)

        # Use AI Tamil title if available, otherwise use original
        if ai_processed and date_details.get("title_tamil"):
            display_title = date_details["title_tamil"]
        else:
            display_title = title

        # Build the announcement
        announcement = f"📢 {source_tamil} அறிவிப்பு\n"
        announcement += "━━━━━━━━━━━━━━━━━━━━\n\n"
        announcement += f"📌 {display_title}\n"

        # Add date details section
        date_section = self._format_date_details_tamil(date_details)
        if date_section:
            announcement += f"\n{date_section}\n"

        announcement += "\n━━━━━━━━━━━━━━━━━━━━\n"

        if url:
            announcement += f'\n🔗 <a href="{url}">அதிகாரப்பூர்வ அறிவிப்பு பார்க்க</a>\n'

        announcement += "\nமேலும் விவரங்களுக்கு அதிகாரப்பூர்வ இணையதளத்தை பார்வையிடவும்.\n\n"
        announcement += '<a href="https://employmenttamil.in/shop/">🛒 விற்பனை நிலையம்</a>'

        # AI credit tag (small, at bottom)
        if ai_processed:
            provider = date_details.get("ai_provider", "")
            if provider:
                announcement += f"\n\n<i>🤖 AI ({provider}) மூலம் பகுப்பாய்வு</i>"

        return announcement

    async def broadcast_notification(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Broadcast a single notification to all channels with rate limiting.

        RATE LIMITING:
        - 0.5 second delay between each channel message
        - On RetryAfter error, waits the specified time + 1s safety, then retries
        """
        bot = Bot(token=self.bot_token)
        message = self._format_tamil_announcement(notification)
        results = {"success": [], "failed": []}

        logger.info(
            f"Broadcasting to {len(self.channel_ids)} channels "
            f"with {BROADCAST_DELAY}s delay between each..."
        )

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

                # ── RATE LIMITING: 0.5s delay between each message ──
                await asyncio.sleep(BROADCAST_DELAY)

            except RetryAfter as e:
                # Telegram explicitly says to wait — respect it
                wait_time = e.retry_after
                logger.warning(
                    f"Rate limited for {channel_id}. "
                    f"Telegram says wait {wait_time}s. Waiting..."
                )
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
                    logger.info(f"Sent to {channel_id} (after retry)")
                except Exception as retry_err:
                    results["failed"].append({
                        "channel": channel_id,
                        "error": f"Retry failed: {str(retry_err)}"
                    })
                    logger.error(f"Failed after retry for {channel_id}: {retry_err}")

            except TelegramError as e:
                error_msg = str(e)
                results["failed"].append({"channel": channel_id, "error": error_msg})

                if "chat not found" in error_msg.lower():
                    logger.warning(f"Channel {channel_id} not found — bot may not be admin")
                elif "bot was blocked" in error_msg.lower():
                    logger.warning(f"Bot blocked in {channel_id}")
                elif "not enough rights" in error_msg.lower():
                    logger.warning(f"Bot lacks post permission in {channel_id}")
                else:
                    logger.error(f"Telegram error for {channel_id}: {e}")

                # Still delay even on error
                await asyncio.sleep(BROADCAST_DELAY)

            except Exception as e:
                results["failed"].append({"channel": channel_id, "error": str(e)})
                logger.error(f"Unexpected error for {channel_id}: {e}")
                await asyncio.sleep(BROADCAST_DELAY)

        success_count = len(results["success"])
        fail_count = len(results["failed"])
        logger.info(
            f"Broadcast complete: {success_count} success, {fail_count} failed "
            f"(~{len(self.channel_ids) * BROADCAST_DELAY:.1f}s total)"
        )
        return results

    async def broadcast_notifications(
        self, notifications: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Broadcast multiple notifications to all channels."""
        if not notifications:
            logger.info("No notifications to broadcast")
            return {"total": 0, "results": []}

        logger.info(
            f"Broadcasting {len(notifications)} notifications "
            f"to {len(self.channel_ids)} channels..."
        )
        all_results = []

        for idx, notification in enumerate(notifications):
            logger.info(
                f"Notification {idx+1}/{len(notifications)}: "
                f"{notification.get('source', '')} - "
                f"{notification.get('title', '')[:50]}..."
            )
            result = await self.broadcast_notification(notification)
            all_results.append({
                "notification": notification.get("title", "")[:100],
                "source": notification.get("source", ""),
                "date_type": notification.get("date_details", {}).get("date_type", "unknown"),
                "ai_processed": notification.get("date_details", {}).get("ai_processed", False),
                "result": result,
            })

            # Extra 1s delay between different notifications
            if idx < len(notifications) - 1:
                await asyncio.sleep(1.0)

        total_success = sum(len(r["result"]["success"]) for r in all_results)
        total_failed = sum(len(r["result"]["failed"]) for r in all_results)
        logger.info(
            f"All broadcasts done: {total_success} sent, "
            f"{total_failed} failed across {len(notifications)} notifications"
        )

        return {"total": len(notifications), "results": all_results}

    def broadcast_notifications_sync(
        self, notifications: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Synchronous wrapper for APScheduler background thread.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.broadcast_notifications(notifications)
            )
        finally:
            loop.close()
