"""
Scraper module for fetching exam date announcements from TNPSC, SSC, and RRB websites.

STRICT RULE: Only notifications containing REAL DATES are kept for broadcasting.
Everything else is silently discarded.
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

# Date patterns — used to verify a real date exists
DATE_PATTERNS = [
    r'\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}',
    r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}',
    r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}',
    r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
]

# Keywords that indicate date-related notifications
DATE_KEYWORDS = [
    "exam date", "examination date", "date of exam", "test date",
    "hall ticket", "admit card", "call letter",
    "last date", "closing date", "deadline",
    "application start", "registration start", "opening date",
    "extension", "extended", "revised last date",
    "postpone", "postponed", "deferred", "rescheduled", "delayed",
    "result", "results declared", "score card", "merit list",
    "schedule", "date sheet", "time table",
]

# Keywords for categorizing date types
DATE_TYPE_KEYWORDS = {
    "exam_date": ["exam date", "examination date", "test date", "written exam", "cbt date"],
    "hall_ticket": ["hall ticket", "admit card", "call letter", "e-admit card"],
    "application_start": ["application start", "apply from", "registration start", "opening date"],
    "application_end": ["last date", "closing date", "deadline", "last date to apply"],
    "date_extension": ["extension", "extended", "revised last date", "extended up to"],
    "postponed": ["postpone", "postponed", "deferred", "rescheduled", "delayed"],
    "result_date": ["result", "results declared", "score card", "merit list"],
}

# URLs to IGNORE (not official government sites)
BLOCKED_DOMAINS = [
    "clasticon.com", "facebook.com", "twitter.com", "youtube.com",
    "instagram.com", "whatsapp.com", "google.com", "play.google.com",
    "apple.com", "microsoft.com",
]


class NotificationScraper:
    """Scrapes exam date notifications — ONLY keeps those with real dates."""

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

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is from an official government site, not a random link."""
        if not url:
            return True  # No URL is fine, we just won't include a link
        url_lower = url.lower()
        for blocked in BLOCKED_DOMAINS:
            if blocked in url_lower:
                return False
        # Only allow government/official URLs
        valid_domains = [
            "tnpsc.gov.in", "ssc.gov.in", "ssc.nic.in",
            "rrbchennai.gov.in", "rrb", ".gov.in", ".nic.in",
        ]
        return any(domain in url_lower for domain in valid_domains)

    def _has_date_in_text(self, text: str) -> bool:
        """Check if text contains any real date pattern."""
        for pattern in DATE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _has_date_keywords(self, text: str) -> bool:
        """Check if text contains date-related keywords."""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in DATE_KEYWORDS)

    def _is_date_relevant(self, text: str) -> bool:
        """
        STRICT FILTER: Only return True if the notification is about dates.
        Must have EITHER a real date pattern OR date-related keywords.
        """
        if self._has_date_in_text(text):
            return True
        if self._has_date_keywords(text):
            return True
        return False

    def _extract_dates_regex(self, text: str) -> List[str]:
        """Extract date strings from text using regex."""
        dates = []
        for pattern in DATE_PATTERNS:
            found = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(found)
        return dates

    def _detect_date_type(self, text: str) -> str:
        """Detect date type from keywords."""
        text_lower = text.lower()
        for date_type, keywords in DATE_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return date_type
        return "notification_date"

    def _extract_date_details_regex(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Regex-based date extraction. Returns None if no real date found.
        """
        dates_found = self._extract_dates_regex(text)
        if not dates_found:
            # No real date in text — SKIP this notification
            return None

        date_type = self._detect_date_type(text)
        details = {
            "date_type": date_type,
            "dates_found": dates_found,
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

        # Associate dates with context
        lines = text.split("\n")
        for line in lines:
            line_lower = line.lower().strip()
            dates_in_line = self._extract_dates_regex(line)
            if dates_in_line:
                if any(kw in line_lower for kw in ["exam date", "examination date", "test date"]):
                    details["specific_dates"]["exam_date"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["hall ticket", "admit card"]):
                    details["specific_dates"]["hall_ticket_date"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["last date", "closing date", "deadline"]):
                    details["specific_dates"]["application_end_date"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["start", "begin", "commencement", "opening"]):
                    details["specific_dates"]["application_start_date"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["result", "merit"]):
                    details["specific_dates"]["result_date"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["extend", "revised"]):
                    details["specific_dates"]["date_extension"] = dates_in_line[0]
                elif any(kw in line_lower for kw in ["postpone", "reschedule", "new date"]):
                    details["specific_dates"]["postponed_to"] = dates_in_line[0]

        # If no specific categorization, put first date under detected type
        if not details["specific_dates"] and dates_found:
            details["specific_dates"][date_type] = dates_found[0]

        return details

    def _extract_date_details(self, text: str, source: str) -> Optional[Dict[str, Any]]:
        """
        Extract date details — tries AI first, falls back to regex.
        Returns None if NO real date is found (notification will be SKIPPED).
        """
        # Try AI processing first
        ai_result = process_notification(text, source)
        if ai_result:
            # AI confirmed has_important_date = True
            details = {
                "date_type": ai_result.get("date_type", "notification_date"),
                "is_extension": ai_result.get("is_extension", False),
                "is_postponed": ai_result.get("is_postponed", False),
                "specific_dates": {},
                "ai_processed": True,
                "title_tamil": ai_result.get("title_tamil", ""),
                "post_name": ai_result.get("post_name", ""),
            }

            # Extract dates from AI response
            ai_dates = ai_result.get("dates", {})
            for key, value in ai_dates.items():
                if value and str(value).lower() not in ("null", "none", ""):
                    details["specific_dates"][key] = value

            # Double-check: AI said important but no actual dates extracted?
            if not details["specific_dates"]:
                logger.info(f"AI said important but no dates extracted for {source}. SKIPPING.")
                return None

            details["dates_found"] = list(details["specific_dates"].values())
            return details

        # AI returned None (no important date) or failed
        # Fallback to regex — but ONLY if text actually has dates
        regex_details = self._extract_date_details_regex(text)
        if regex_details:
            logger.info(f"Regex found dates for {source}: {regex_details.get('specific_dates', {})}")
            return regex_details

        # No dates found by either method — DO NOT broadcast
        return None

    def _fetch_page(self, url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
        try:
            response = self.session.get(url, timeout=timeout, verify=False)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def scrape_tnpsc(self) -> List[Dict[str, Any]]:
        """Scrape TNPSC notifications — only keep those with dates."""
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
                            if text.strip() and len(text.strip()) > 15:
                                items.append((text.strip(), link_url))

                seen_texts = set()
                for text, link_url in items[:30]:
                    if text in seen_texts or len(text) < 15:
                        continue
                    seen_texts.add(text)

                    # FILTER 1: Must be date-relevant
                    if not self._is_date_relevant(text):
                        continue

                    # FILTER 2: URL must be valid (no random external links)
                    if not self._is_valid_url(link_url):
                        link_url = "https://www.tnpsc.gov.in/"

                    content = f"TNPSC: {text}"
                    if self._is_new_notification(content):
                        # FILTER 3: Must have extractable dates
                        date_details = self._extract_date_details(text, "TNPSC")
                        if date_details is None:
                            logger.info(f"TNPSC: No real date found, skipping: {text[:80]}")
                            continue

                        notifications.append({
                            "source": "TNPSC",
                            "title": text[:500],
                            "url": link_url,
                            "timestamp": datetime.now().isoformat(),
                            "date_details": date_details,
                        })

                logger.info(f"TNPSC {page_name}: {len(notifications)} date notifications found")

            except Exception as e:
                logger.error(f"Error scraping TNPSC ({page_name}): {e}")

        return notifications

    def scrape_ssc(self) -> List[Dict[str, Any]]:
        """Scrape SSC notifications — only keep those with dates."""
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
                            if text and len(text) > 15:
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
                    if text in seen_texts or len(text) < 15:
                        continue
                    seen_texts.add(text)

                    # FILTER 1: Must be date-relevant
                    if not self._is_date_relevant(text):
                        continue

                    # FILTER 2: URL must be valid
                    if not self._is_valid_url(link_url):
                        link_url = "https://ssc.gov.in/"

                    content = f"SSC: {text}"
                    if self._is_new_notification(content):
                        # FILTER 3: Must have extractable dates
                        date_details = self._extract_date_details(text, "SSC")
                        if date_details is None:
                            logger.info(f"SSC: No real date found, skipping: {text[:80]}")
                            continue

                        notifications.append({
                            "source": "SSC",
                            "title": text[:500],
                            "url": link_url,
                            "timestamp": datetime.now().isoformat(),
                            "date_details": date_details,
                        })

                logger.info(f"SSC ({url}): {len(notifications)} date notifications found")
                if items:
                    break

            except Exception as e:
                logger.error(f"Error scraping SSC ({url}): {e}")

        return notifications

    def scrape_rrb(self) -> List[Dict[str, Any]]:
        """Scrape RRB notifications — only keep those with dates."""
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
                            if text.strip() and len(text.strip()) > 15:
                                items.append((text.strip(), link_url))

                seen_texts = set()
                for text, link_url in items[:20]:
                    if text in seen_texts or len(text) < 15:
                        continue
                    seen_texts.add(text)

                    # FILTER 1: Must be date-relevant
                    if not self._is_date_relevant(text):
                        continue

                    # FILTER 2: URL must be valid
                    if not self._is_valid_url(link_url):
                        link_url = "https://www.rrbchennai.gov.in/"

                    content = f"RRB: {text}"
                    if self._is_new_notification(content):
                        # FILTER 3: Must have extractable dates
                        date_details = self._extract_date_details(text, "RRB Chennai")
                        if date_details is None:
                            logger.info(f"RRB: No real date found, skipping: {text[:80]}")
                            continue

                        notifications.append({
                            "source": "RRB Chennai",
                            "title": text[:500],
                            "url": link_url,
                            "timestamp": datetime.now().isoformat(),
                            "date_details": date_details,
                        })

                logger.info(f"{site_name}: {len(notifications)} date notifications found")

            except Exception as e:
                logger.error(f"Error scraping {site_name}: {e}")

        return notifications

    def scrape_all(self) -> List[Dict[str, Any]]:
        """Scrape all sources — returns ONLY notifications with real dates."""
        all_notifications = []
        logger.info("=" * 50)
        logger.info("Starting scrape — ONLY broadcasting notifications with REAL DATES")

        ai_status = is_ai_available()
        if ai_status["any_available"]:
            logger.info("AI processing: ENABLED (strict date filtering)")
        else:
            logger.info("AI processing: DISABLED (using regex date filtering)")

        tnpsc_notifs = self.scrape_tnpsc()
        all_notifications.extend(tnpsc_notifs)
        logger.info(f"TNPSC: {len(tnpsc_notifs)} notifications WITH dates")

        ssc_notifs = self.scrape_ssc()
        all_notifications.extend(ssc_notifs)
        logger.info(f"SSC: {len(ssc_notifs)} notifications WITH dates")

        rrb_notifs = self.scrape_rrb()
        all_notifications.extend(rrb_notifs)
        logger.info(f"RRB: {len(rrb_notifs)} notifications WITH dates")

        logger.info(f"Total notifications to broadcast: {len(all_notifications)}")
        if len(all_notifications) == 0:
            logger.info("No new date announcements found. Nothing to broadcast.")
        logger.info("=" * 50)
        return all_notifications
