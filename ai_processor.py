"""
AI Processor module for intelligent date extraction and Tamil translation.
Uses Groq (primary, free tier) with Gemini as fallback.

All API keys are loaded from environment variables — NEVER hardcoded.
Set them in Render dashboard or .env file locally.
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

# System prompt for extracting dates and translating to Tamil
SYSTEM_PROMPT = """You are an expert Tamil government exam notification analyzer.

Your job is to analyze government exam notifications from TNPSC, SSC, and RRB and extract ALL important dates and details.

For each notification, extract and return a JSON object with these fields:
{
  "title_tamil": "Notification title translated to simple Tamil",
  "summary_tamil": "Brief 1-2 line summary in Tamil",
  "dates": {
    "exam_date": "date or null",
    "hall_ticket_date": "date or null",
    "application_start_date": "date or null",
    "application_end_date": "date or null",
    "date_extension": "date or null",
    "postponed_to": "date or null",
    "result_date": "date or null",
    "notification_date": "date or null"
  },
  "date_type": "one of: exam_date, hall_ticket, application_start, application_end, date_extension, postponed, result_date, notification_date",
  "is_extension": true/false,
  "is_postponed": true/false,
  "post_name": "Name of the post/exam in Tamil",
  "important_note_tamil": "Any important note in Tamil or null"
}

Rules:
- Translate everything to simple, clear Tamil
- Keep dates in DD.MM.YYYY format
- If a date is not mentioned, set it to null
- Detect if this is a date extension or postponement
- Be accurate — do not guess dates that are not in the text
- Return ONLY valid JSON, no extra text"""


def _try_parse_json(text: str) -> Optional[Dict]:
    """Try to parse JSON from AI response, handling markdown code blocks."""
    # Remove markdown code block if present
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
        # Try to find JSON object in the text
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

    Args:
        notification_text: Raw notification text
        source: Source website (TNPSC, SSC, RRB)

    Returns:
        Processed notification dict or None on failure
    """
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set, skipping Groq processing")
        return None

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)

        user_message = (
            f"Source: {source}\n"
            f"Notification text:\n{notification_text}\n\n"
            f"Extract all dates and translate to Tamil. Return JSON only."
        )

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1000,
            temperature=0.1,
        )

        result_text = response.choices[0].message.content
        parsed = _try_parse_json(result_text)

        if parsed:
            logger.info(f"Groq processed successfully: {source}")
            return parsed
        else:
            logger.warning(f"Groq returned non-JSON response: {result_text[:200]}")
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

    Args:
        notification_text: Raw notification text
        source: Source website (TNPSC, SSC, RRB)

    Returns:
        Processed notification dict or None on failure
    """
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set, skipping Gemini processing")
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Source: {source}\n"
            f"Notification text:\n{notification_text}\n\n"
            f"Extract all dates and translate to Tamil. Return JSON only."
        )

        response = model.generate_content(prompt)
        result_text = response.text
        parsed = _try_parse_json(result_text)

        if parsed:
            logger.info(f"Gemini processed successfully: {source}")
            return parsed
        else:
            logger.warning(f"Gemini returned non-JSON response: {result_text[:200]}")
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
    If both fail, returns None (the bot will use basic regex extraction).

    Args:
        notification_text: Raw notification text
        source: Source website (TNPSC, SSC, RRB)

    Returns:
        AI-processed notification dict or None
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

    # Both failed
    logger.warning(
        f"Both AI providers failed for {source} notification. "
        f"Falling back to basic extraction."
    )
    return None


def is_ai_available() -> Dict[str, bool]:
    """
    Check which AI providers are configured.

    Returns:
        Dict with availability status for each provider
    """
    return {
        "groq": bool(GROQ_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
        "any_available": bool(GROQ_API_KEY or GEMINI_API_KEY),
    }
