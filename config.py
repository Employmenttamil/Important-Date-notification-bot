"""
Configuration module for the Exam Date Bot.
Manages bot token, channel list, and other settings.

SECURITY: All sensitive values (bot token, API keys) are loaded from
environment variables ONLY. Never hardcode secrets in this file.
Set them in Render dashboard or local .env file.
"""

import os
from typing import List

# ──────────────────────────────────────────────
# TELEGRAM BOT TOKEN (from environment variable)
# Set in Render dashboard: TELEGRAM_BOT_TOKEN
# ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ──────────────────────────────────────────────
# AI API KEYS (from environment variables)
# Groq = primary (free tier, fast)
# Gemini = fallback (free tier)
# Set in Render dashboard: GROQ_API_KEY, GEMINI_API_KEY
# ──────────────────────────────────────────────
# (Loaded directly in ai_processor.py from env vars)

# ──────────────────────────────────────────────
# Public channels (72 channels, accessed by @username)
# ──────────────────────────────────────────────
PUBLIC_CHANNELS = [
    "@FULL_MOVIE_DATABASE",
    "@Eternals_disneyplus",
    "@freeonlinetestse",
    "@TNPSCASPIRANTTHOZAN",
    "@hsjvdodmndk",
    "@maduraipakkam",
    "@Mr_kn_TG",
    "@Sundar_Jayanth",
    "@Tnpsc_mattum_pothumaa",
    "@pngconverter_bot",
    "@kalamtnpsccoachingcentre",
    "@dghkkjffvh",
    "@TNPSC_Mattum_Pothuma",
    "@kannavu",
    "@Tnusrb_Police_Si_Exam_Tamil",
    "@pyro_userbot",
    "@TeleGiG_EmployBot",
    "@annamalai_k",
    "@zohoexamdiscussiongroup",
    "@EETYjobs",
    "@AutoMobileOpenBookAnswers",
    "@TN_BJP_it_wing",
    "@infomesfc",
    "@Vivek_ice_men",
    "@Tnpsc_Free_Test_Pdf",
    "@Maxton_Hall_Tamil_Download",
    "@santhoshmanitnpsc",
    "@mba_a22",
    "@Employment_News_Paper_Tamil",
    "@Under_Paris_Tamil_Download",
    "@Gutar_Gu_Tamil_Download",
    "@Arun_sk",
    "@Tnpsc_Group04",
    "@nivisha199807",
    "@sankartnpsctestbatch",
    "@tamilsaraltech",
    "@preparetocrack",
    "@tnpscgeneralenglishaspirant",
    "@TNPSCTNUSRBDQUIZ",
    "@tnpsc0fficial",
    "@virutchamtnpsc",
    "@TNPSC_MATTUM_POTHUMAAA",
    "@Jobs_in_Chennai_Local",
    "@draramadoss",
    "@AIADMKITWINGOFL",
    "@tnpscgeneralenglishgroup",
    "@inforVERSE",
    "@Engineering_Ask",
    "@tnpscfreequizz",
    "@prepforfuture",
    "@maduraiyar",
    "@jrtnpsc",
    "@GLl4_VKVfPLaVCoygF71iw",
    "@Test_Serious",
    "@neovao",
    "@NirmalChristo_CWC",
    "@SavukkuOfficial",
    "@tnpscallstudy",
    "@tnpscofficiall",
    "@seerudai",
    "@tamilnadupolice24",
    "@manithaneyamiasacadamy",
    "@ai_tnpsc",
    "@tgpsc2024",
    "@KMF_TNPSCAcademy",
    "@smartworktnpsc",
    "@kalvi_vaagai",
    "@target125125TNPSC",
    "@thirumaofficial",
    "@ARMTNPSC",
    "@tn_psc_usrb_fusrb",
    "@employmenttamil",
]

# ──────────────────────────────────────────────
# Private channels (24 channels, accessed by numeric ID)
# Private channels require -100 prefix for Telegram Bot API
# ──────────────────────────────────────────────
PRIVATE_CHANNELS = [
    "-1001655625927",
    "-1001834093615",
    "-1001837437389",
    "-1001887708386",
    "-1001885403640",
    "-1002087326522",
    "-1002082356851",
    "-1002119132551",
    "-1002186166125",
    "-1002179061654",
    "-1002173248385",
    "-1002206005285",
    "-1002203648737",
    "-1002190957882",
    "-1002211468849",
    "-1002210363948",
    "-1002208929554",
    "-1002234444004",
    "-1002224157160",
    "-1002223231366",
    "-1002244166756",
    "-1002243560534",
    "-1002240177506",
    "-1002310768925",
]

# Combined default list: 72 public + 24 private = 96 channels
DEFAULT_CHANNELS = PUBLIC_CHANNELS + PRIVATE_CHANNELS


def get_channel_ids() -> List[str]:
    """
    Get list of channel IDs from environment or default.
    TELEGRAM_CHANNEL_ID env var accepts comma-separated channel usernames/IDs.
    Supports both @username (public) and -100xxxx (private) formats.
    """
    channel_env = os.getenv("TELEGRAM_CHANNEL_ID", "")
    if channel_env:
        return [ch.strip() for ch in channel_env.split(",") if ch.strip()]
    return DEFAULT_CHANNELS


# Scraping configuration
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "30"))

# Flask configuration
FLASK_PORT = int(os.getenv("PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"

# Render configuration
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")

# Webhook configuration
WEBHOOK_PATH = "/webhook/telegram"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else ""

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# File storage
SEEN_NOTIFICATIONS_FILE = "seen_notifications.json"
