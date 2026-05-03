"""
Scraper module for fetching exam date announcements from TNPSC, SSC, and RRB websites.
Uses AI (Groq/Gemini) for smart date extraction and Tamil translation.
Falls back to regex-based extraction if AI is unavailable.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
import hashlib

from ai_processor import process_notification, is_ai_available

logger = logging.getLogger(__name__)

# Date patterns to extract from notification text (regex fallback)
DATE_PATTERNS = [
    r'\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}',
    r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}',
    r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}',
]

# Keywords for categorizing date types (regex fallback)
DATE_TYPE_KEYWORDS = {
    "exam_date": [
        "exam date", "examination date", "date of exam", "test date",
        "written exam", "written test", "cbt date", "online exam",
    ],
    "hall_ticket": [
        "hall ticket", "admit card", "admission certificate",
        "e-admit card", "call letter",
    ],
    "application_start": [
        "application start", "apply from", "registration start",
        "commencement of application", "opening date",
    ],
    "application_end": [
        "last date", "application end", "closing date",
        "last date to apply", "deadline", "last date for submission",
    ],
    "date_extension": [
        "extension", "extended", "date extended",
        "revised last date", "extended up to",
    ],
    "postponed": [
        "postpone", "postponed", "deferred", "rescheduled",
        "delayed", "held in abeyance",
    ],
    "result_date": [
        "result", "results declared", "result date",
        "score card", "merit list", "final result",
    ],
    "notification_date": [
        "notification", "advertisement", "recruitment notification",
        "vacancy notification",
    ],
}

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
    "postponed": "⚠️ தேர்வு ஒத்திவைப்பு / தாமதம்",
    "postponed_to": "⚠️ ஒத்திவைக்கப்பட்ட புதிய நாள்",
    "result_date": "📊 முடிவு வெளியீடு",
    "notification_date": "📢 அறிவிப்பு நாள்",
    "extended_date": "📅 நீட்டிக்கப்பட்ட நாள்",
    "new_date": "🔄 புதிய நாள்",
}


class NotificationScraper:
    """Scrapes exam date notifications from government recruitment websites."""

    def __init__(self, seen_file: str = "seen_notifications.json"):
        self.seen_file = seen_file
        self.seen_hashes = self._load_seen_hashes()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Check AI availability
        ai_status = is_ai_available()
        if ai_status["any_available"]:
            providers = []
            if ai_status["groq"]:
                providers.append("Groq")
            if ai_status["gemini"]:
                providers.append("Gemini")
            logger.info(f"AI processing enabled: {', '.join(providers)}")
        else:
            logger.warning("No AI API keys configured. Using basic regex extraction.")

    def _load_seen_hashes(self) -> set:
        if os.path.exists(self.seen_file):
            try:
                with open(self.seen_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get("hashes", []))
            except Exception as e:
                logger.warning(f"Failed to load seen hashes: {e}")
        return set()

    def _save_seen_hashes(self) -> None:
        try:
            with open(self.seen_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "hashes": list(self.seen_hashes),
                        "updated_at": datetime.now().isoformat(),
                        "total_seen": len(self.seen_hashes),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"Failed to save seen hashes: {e}")

    def _generate_hash(self, content: str) -> str:
        return hashlib.sha256(content.strip().lower().encode("utf-8")).hexdigest()

    def _is_new_notification(self, content: str) -> bool:
        content_hash = self._generate_hash(content)
        if content_hash in self.seen_hashes:
            return False
        self.seen_hashes.add(content_hash)
        self._save_seen_hashes()
        return True

    def _extract_dates_regex(self, text: str) -> List[str]:
        """Regex fallback: extract date strings from text."""
        dates = []
        for pattern in DATE_PATTERNS:
            found = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(found)
        return dates

    def _detect_date_type_regex(self, text: str) -> str:
        """Regex fallback: detect date type from keywords."""
        text_lower = text.lower()
        for date_type, keywords in DATE_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return date_type
        return "notification_date"

    def _extract_date_details_regex(self, text: str) -> Dict[str, Any]:
        """
        Regex fallback: extract date details when AI is unavailable.
        """
        details = {
            "date_type": self._detect_date_type_regex(text),
            "dates_found": self._extract_dates_regex(text),
            "is_extension": False,
            "is_postponed": False,
            "specific_dates": {},
            "ai_processed": False,
        }

        text_lower = text.lower()

        if any(kw in text_lower for kw in ["extend", "extension", "revised last date"]):
            details["is_extension"] = True
            details["date_type"] = "date_extension"

        if any(kw in text_lower for kw in ["postpone", "defer", "reschedule", "delay"]):
            details["is_postponed"] = True
            details["date_type"] = "postponed"

        # Try to associate dates with their context
        lines = text.split("\n")
        for line in lines:
            line_lower = line.lower().strip()
            dates_in_line = self._extract_dates_regex(line)
            if dates_in_line:
                if any(kw in line_lower for kw in ["exam date", "examination date", "test date"]):
                    details["specific_dates"]["exam_date"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["hall ticket", "admit card"]):
                    details["specific_dates"]["hall_ticket"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["last date", "closing date", "deadline"]):
                    details["specific_dates"]["application_end"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["start", "begin", "commencement", "opening"]):
                    details["specific_dates"]["application_start"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["result", "merit"]):
                    details["specific_dates"]["result_date"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["extend", "revised"]):
                    details["specific_dates"]["extended_date"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["postpone", "reschedule", "new date"]):
                    details["specific_dates"]["new_date"] = dates_in_line[0]

        if not details["specific_dates"] and details["dates_found"]:
            details["specific_dates"][details["date_type"]] = details["dates_found"][0]

        return details

    def _extract_date_details_ai(self, text: str, source: str) -> Optional[Dict[str, Any]]:
        """
        AI-powered date extraction using Groq (primary) or Gemini (fallback).
        Returns structured date details or None if AI fails.
        """
        ai_result = process_notification(text, source)
        if not ai_result:
            return None

        # Convert AI result to our standard format
        details = {
            "date_type": ai_result.get("date_type", "notification_date"),
            "is_extension": ai_result.get("is_extension", False),
            "is_postponed": ai_result.get("is_postponed", False),
            "specific_dates": {},
            "ai_processed": True,
            "ai_provider": ai_result.get("_ai_provider", "unknown"),
            "title_tamil": ai_result.get("title_tamil", ""),
            "summary_tamil": ai_result.get("summary_tamil", ""),
            "post_name": ai_result.get("post_name", ""),
            "important_note_tamil": ai_result.get("important_note_tamil", ""),
        }

        # Extract dates from AI response
        ai_dates = ai_result.get("dates", {})
        for key, value in ai_dates.items():
            if value and value != "null" and str(value).lower() != "none":
                details["specific_dates"][key] = value

        # Collect all found dates
        details["dates_found"] = list(details["specific_dates"].values())

        return details

    def _extract_date_details(self, text: str, source: str) -> Dict[str, Any]:
        """
        Extract date details — tries AI first, falls back to regex.

        Args:
            text: Notification text
            source: Source website name

        Returns:
            Dictionary with extracted date details
        """
        # Try AI processing first
        ai_details = self._extract_date_details_ai(text, source)
        if ai_details:
            logger.info(f"AI extracted dates for {source}: {ai_details.get('specific_dates', {})}")
            return ai_details

        # Fallback to regex
        regex_details = self._extract_date_details_regex(text)
        logger.info(f"Regex extracted dates for {source}: {regex_details.get('specific_dates', {})}")
        return regex_details

    def _fetch_page(self, url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
        try:
            response = self.session.get(url, timeout=timeout, verify=False)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def scrape_tnpsc(self) -> List[Dict[str, Any]]:
        """Scrape TNPSC notifications."""
        notifications = []
        urls = [
            ("https://www.tnpsc.gov.in/english/whatsnew.html", "What's New"),
            ("https://www.tnpsc.gov.in/english/notification.aspx", "Notifications"),
        ]

        for url, page_name in urls:
            try:
                soup = self._fetch_page(url)
                if not soup:
                    continue

                items = []

                for table in soup.find_all("table"):
                    rows = table.find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if cols:
                            text = " ".join(col.get_text(strip=True) for col in cols)
                            link = row.find("a")
                            link_url = ""
                            if link and link.get("href"):
                                href = link["href"]
                                if not href.startswith("http"):
                                    href = f"https://www.tnpsc.gov.in/{href}"
                                link_url = href
                            if text.strip() and len(text.strip()) > 10:
                                items.append((text.strip(), link_url))

                for link in soup.find_all("a"):
                    text = link.get_text(strip=True)
                    href = link.get("href", "")
                    if text and len(text) > 10:
                        if not href.startswith("http"):
                            href = f"https://www.tnpsc.gov.in/{href}"
                        items.append((text, href))

                seen_texts = set()
                for text, link_url in items[:30]:
                    if text in seen_texts or len(text) < 10:
                        continue
                    seen_texts.add(text)

                    content = f"TNPSC: {text}"
                    if self._is_new_notification(content):
                        date_details = self._extract_date_details(text, "TNPSC")
                        notifications.append({
                            "source": "TNPSC",
                            "title": text[:500],
                            "url": link_url,
                            "timestamp": datetime.now().isoformat(),
                            "date_details": date_details,
                        })

                logger.info(f"TNPSC {page_name}: processed {len(seen_texts)} items")

            except Exception as e:
                logger.error(f"Error scraping TNPSC ({page_name}): {e}")

        return notifications

    def scrape_ssc(self) -> List[Dict[str, Any]]:
        """Scrape SSC notifications."""
        notifications = []
        urls = [
            "https://ssc.gov.in/",
            "https://ssc.nic.in/",
        ]

        for url in urls:
            try:
                soup = self._fetch_page(url)
                if not soup:
                    continue

                items = []

                for selector in [
                    "div.news-item", "li.notification", "div.notice",
                    "marquee", "div.scrollbar", "div.latest-news",
                    "div.what-new", "div.whats-new",
                ]:
                    elements = soup.select(selector)
                    for elem in elements:
                        for link in elem.find_all("a"):
                            text = link.get_text(strip=True)
                            href = link.get("href", "")
                            if text and len(text) > 10:
                                if not href.startswith("http"):
                                    href = f"https://ssc.gov.in/{href}"
                                items.append((text, href))

                for link in soup.find_all("a"):
                    text = link.get_text(strip=True)
                    href = link.get("href", "")
                    if text and len(text) > 15 and href.endswith((".pdf", ".html", ".aspx")):
                        if not href.startswith("http"):
                            href = f"https://ssc.gov.in/{href}"
                        items.append((text, href))

                seen_texts = set()
                for text, link_url in items[:20]:
                    if text in seen_texts or len(text) < 10:
                        continue
                    seen_texts.add(text)

                    content = f"SSC: {text}"
                    if self._is_new_notification(content):
                        date_details = self._extract_date_details(text, "SSC")
                        notifications.append({
                            "source": "SSC",
                            "title": text[:500],
                            "url": link_url,
                            "timestamp": datetime.now().isoformat(),
                            "date_details": date_details,
                        })

                logger.info(f"SSC ({url}): processed {len(seen_texts)} items")
                if items:
                    break

            except Exception as e:
                logger.error(f"Error scraping SSC ({url}): {e}")

        return notifications

    def scrape_rrb(self) -> List[Dict[str, Any]]:
        """Scrape RRB notifications."""
        notifications = []
        rrb_sites = [
            ("https://www.rrbchennai.gov.in/", "RRB Chennai"),
            ("https://www.rrbchennai.gov.in/ImportantNotices.html", "RRB Chennai Notices"),
        ]

        for url, site_name in rrb_sites:
            try:
                soup = self._fetch_page(url)
                if not soup:
                    continue

                items = []

                for table in soup.find_all("table"):
                    rows = table.find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if cols:
                            text = " ".join(col.get_text(strip=True) for col in cols)
                            link = row.find("a")
                            link_url = ""
                            if link and link.get("href"):
                                href = link["href"]
                                if not href.startswith("http"):
                                    href = f"https://www.rrbchennai.gov.in/{href}"
                                link_url = href
                            if text.strip() and len(text.strip()) > 10:
                                items.append((text.strip(), link_url))

                for link in soup.find_all("a"):
                    text = link.get_text(strip=True)
                    href = link.get("href", "")
                    if text and len(text) > 10:
                        if not href.startswith("http"):
                            href = f"https://www.rrbchennai.gov.in/{href}"
                        items.append((text, href))

                seen_texts = set()
                for text, link_url in items[:20]:
                    if text in seen_texts or len(text) < 10:
                        continue
                    seen_texts.add(text)

                    content = f"RRB: {text}"
                    if self._is_new_notification(content):
                        date_details = self._extract_date_details(text, "RRB Chennai")
                        notifications.append({
                            "source": "RRB Chennai",
                            "title": text[:500],
                            "url": link_url,
                            "timestamp": datetime.now().isoformat(),
                            "date_details": date_details,
                        })

                logger.info(f"{site_name}: processed {len(seen_texts)} items")

            except Exception as e:
                logger.error(f"Error scraping {site_name}: {e}")

        return notifications

    def scrape_all(self) -> List[Dict[str, Any]]:
        """Scrape all sources and return new notifications."""
        all_notifications = []
        logger.info("=" * 50)
        logger.info("Starting scrape of all sources...")

        ai_status = is_ai_available()
        if ai_status["any_available"]:
            logger.info("AI processing: ENABLED")
        else:
            logger.info("AI processing: DISABLED (no API keys)")

        tnpsc_notifs = self.scrape_tnpsc()
        all_notifications.extend(tnpsc_notifs)
        logger.info(f"TNPSC: {len(tnpsc_notifs)} new notifications")

        ssc_notifs = self.scrape_ssc()
        all_notifications.extend(ssc_notifs)
        logger.info(f"SSC: {len(ssc_notifs)} new notifications")

        rrb_notifs = self.scrape_rrb()
        all_notifications.extend(rrb_notifs)
        logger.info(f"RRB: {len(rrb_notifs)} new notifications")

        logger.info(f"Total new notifications: {len(all_notifications)}")
        logger.info("=" * 50)
        return all_notifications
