"""
AI Processor module for intelligent date extraction and Tamil translation.
Uses Groq (primary, free tier) with Gemini as fallback.

STRICT RULE: Only returns data when a REAL DATE is found in the notification.
If no actual date (DD.MM.YYYY or similar) exists, returns None — meaning NO broadcast.

All API keys are loaded from environment variables — NEVER hardcoded.
"""

import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# API keys from environment variables ONLY
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Groq model (free tier)
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# Gemini model (free tier)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# System prompt — strict date-only extraction
SYSTEM_PROMPT = """You are a Tamil government exam date extractor. You ONLY extract REAL DATES from notifications.

STRICT RULES:
1. ONLY return data if the notification contains at least ONE real date (like 15.06.2026, June 15 2026, etc.)
2. If there is NO real date in the notification, you MUST return: {"has_important_date": false}
3. Do NOT make up dates. Do NOT guess dates. Only extract dates that are explicitly written.
4. Ignore general website descriptions, disclaimers, copyright notices, navigation links.
5. Only focus on: exam dates, hall ticket dates, application start/end dates, date extensions, postponements, result dates.

If a REAL DATE exists, return this JSON:
{
  "has_important_date": true,
  "title_tamil": "Short title in Tamil (exam name + what the date is about)",
  "dates": {
    "exam_date": "DD.MM.YYYY or null",
    "hall_ticket_date": "DD.MM.YYYY or null",
    "application_start_date": "DD.MM.YYYY or null",
    "application_end_date": "DD.MM.YYYY or null",
    "date_extension": "DD.MM.YYYY or null",
    "postponed_to": "DD.MM.YYYY or null",
    "result_date": "DD.MM.YYYY or null"
  },
  "date_type": "exam_date|hall_ticket|application_start|application_end|date_extension|postponed|result_date",
  "is_extension": true/false,
  "is_postponed": true/false,
  "post_name": "Name of post/exam in Tamil"
}

If NO real date exists, return ONLY:
{"has_important_date": false}

Return ONLY valid JSON. No extra text."""


def _try_parse_json(text: str) -> Optional[Dict]:
    """Try to parse JSON from AI response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                return None
    return None


def process_with_groq(notification_text: str, source: str) -> Optional[Dict[str, Any]]:
    """
    Process notification using Groq API (Llama 3.1, free tier).
    Returns None if no important date found or on failure.
    """
    if not GROQ_API_KEY:
        return None

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)

        user_message = (
            f"Source: {source}\n"
            f"Notification text:\n{notification_text}\n\n"
            f"Does this contain a REAL DATE? If yes, extract it. If no, return has_important_date: false."
        )

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=800,
            temperature=0.0,
        )

        result_text = response.choices[0].message.content
        parsed = _try_parse_json(result_text)

        if parsed:
            # STRICT CHECK: Only return if has_important_date is True
            if not parsed.get("has_important_date", False):
                logger.info(f"Groq: No important date found in {source} notification. SKIPPING.")
                return None
            logger.info(f"Groq: Important date found in {source} notification.")
            return parsed
        else:
            logger.warning(f"Groq returned non-JSON: {result_text[:200]}")
            return None

    except ImportError:
        logger.error("groq package not installed. Run: pip install groq")
        return None
    except Exception as e:
        logger.error(f"Groq processing failed: {e}")
        return None


def process_with_gemini(notification_text: str, source: str) -> Optional[Dict[str, Any]]:
    """
    Process notification using Gemini API (free tier fallback).
    Returns None if no important date found or on failure.
    """
    if not GEMINI_API_KEY:
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Source: {source}\n"
            f"Notification text:\n{notification_text}\n\n"
            f"Does this contain a REAL DATE? If yes, extract it. If no, return has_important_date: false."
        )

        response = model.generate_content(prompt)
        result_text = response.text
        parsed = _try_parse_json(result_text)

        if parsed:
            if not parsed.get("has_important_date", False):
                logger.info(f"Gemini: No important date found in {source} notification. SKIPPING.")
                return None
            logger.info(f"Gemini: Important date found in {source} notification.")
            return parsed
        else:
            logger.warning(f"Gemini returned non-JSON: {result_text[:200]}")
            return None

    except ImportError:
        logger.error("google-generativeai package not installed")
        return None
    except Exception as e:
        logger.error(f"Gemini processing failed: {e}")
        return None


def process_notification(notification_text: str, source: str) -> Optional[Dict[str, Any]]:
    """
    Process notification with AI — tries Groq first, falls back to Gemini.
    Returns None if:
    - No real date found in the notification
    - Both AI providers fail

    This ensures ONLY date-containing notifications get broadcast.
    """
    # Try Groq first (primary — free tier, fast)
    result = process_with_groq(notification_text, source)
    if result:
        result["_ai_provider"] = "groq"
        return result

    # Fallback to Gemini
    result = process_with_gemini(notification_text, source)
    if result:
        result["_ai_provider"] = "gemini"
        return result

    # Both failed — return None (notification will be checked by regex)
    logger.warning(f"Both AI providers failed for {source}. Will use regex fallback.")
    return None


def is_ai_available() -> Dict[str, bool]:
    """Check which AI providers are configured."""
    return {
        "groq": bool(GROQ_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
        "any_available": bool(GROQ_API_KEY or GEMINI_API_KEY),
    }
