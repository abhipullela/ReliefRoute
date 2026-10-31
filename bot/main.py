"""
bot/main.py — ReliefRoute Telegram Dispatch Bot (Member C)

Responsibilities
----------------
1. LOCATION INGESTION  — receive live GPS shares from drivers and POST them to
   POST /api/v1/driver-locations  (DriverLocation schema).

2. DRIVER ACKNOWLEDGEMENT — receive free-text replies (e.g. "Received", "OK")
   from drivers and POST them to
   POST /api/v1/plans/{plan_id}/acknowledgements  (DriverAcknowledgement schema).

3. OUTBOUND DISPATCHER — expose `send_dispatch_message(...)` for the FastAPI
   backend to call; returns the Telegram message ID as a str.

Strict separation: "message SENT" (Telegram accepted it) is tracked entirely
separately from "driver ACKNOWLEDGED" (driver replied). Never conflate them.

Environment variables (from .env):
  TELEGRAM_BOT_TOKEN      — required
  TELEGRAM_WEBHOOK_SECRET — used when running in webhook mode (optional for polling)
  API_BASE_URL            — base URL for the internal API, default http://127.0.0.1:8000
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from dotenv import load_dotenv
from telegram import Bot, Message, Update
from telegram.error import BadRequest, NetworkError, TelegramError, TimedOut
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("reliefroute.bot")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_BASE_URL: str = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# When a driver sends a text message we need a plan_id to attach the ack to.
# The bot resolves this via context.chat_data keyed by "active_plan_id".
# The FastAPI backend sets this when dispatching (see send_dispatch_message).
_ACTIVE_PLAN_KEY = "active_plan_id"
_DRIVER_ID_KEY = "driver_id"

# ---------------------------------------------------------------------------
# Shared async HTTP client
# ---------------------------------------------------------------------------

_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


def _api_url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


async def _post(path: str, payload: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(_api_url(path), json=payload)
    return resp


# ---------------------------------------------------------------------------
# HANDLER 1 — Location ingestion
# ---------------------------------------------------------------------------

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Triggered when a driver shares a live GPS location or a static location pin.
    Parses coordinates and POSTs a DriverLocation to /api/v1/driver-locations.
    """
    if update.message is None or update.message.location is None:
        return

    loc = update.message.location
    chat_id = str(update.effective_chat.id)
    driver_id: str = context.chat_data.get(_DRIVER_ID_KEY, chat_id)

    observed_at = datetime.now(timezone.utc).isoformat()

    payload: dict[str, Any] = {
        "driver_id": driver_id,
        "location": {
            "latitude": loc.latitude,
            "longitude": loc.longitude,
        },
        "observed_at": observed_at,
        "source": "telegram_live_share" if loc.live_period else "telegram_pin",
        "accuracy_m": loc.horizontal_accuracy if loc.horizontal_accuracy else None,
        "consented": True,
    }

    logger.info(
        "Location received from driver_id=%s  lat=%.6f lon=%.6f  live=%s",
        driver_id, loc.latitude, loc.longitude, bool(loc.live_period),
    )

    try:
        resp = await _post("/api/v1/driver-locations", payload)
        if resp.status_code in (200, 201):
            logger.info("Location recorded for driver_id=%s  status=%s", driver_id, resp.status_code)
        elif resp.status_code == 409:
            logger.warning("Idempotency conflict recording location for driver_id=%s", driver_id)
        else:
            logger.error(
                "API error recording location for driver_id=%s  status=%s  body=%s",
                driver_id, resp.status_code, resp.text[:500],
            )
    except httpx.TimeoutException:
        logger.error("Timeout posting location for driver_id=%s", driver_id)
    except httpx.RequestError as exc:
        logger.error("Network error posting location for driver_id=%s: %s", driver_id, exc)


# ---------------------------------------------------------------------------
# HANDLER 2 — Driver acknowledgement (text replies)
# ---------------------------------------------------------------------------

# Patterns that count as an acknowledgement. Case-insensitive.
_ACK_PATTERNS = re.compile(
    r"\b(received|ack|acknowledged|ok|okay|got it|on my way|understood|noted|yes|confirmed)\b",
    re.IGNORECASE,
)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Triggered on any text message from a driver.
    If the message looks like an acknowledgement and an active plan_id exists
    for this chat, POST a DriverAcknowledgement to the API.

    NOTE: This is strictly separate from 'message SENT'.  Receiving this reply
    means the driver has acknowledged; it does NOT retroactively change the
    SENT dispatch record.
    """
    if update.message is None or not update.message.text:
        return

    chat_id = str(update.effective_chat.id)
    text = update.message.text.strip()
    driver_id: str = context.chat_data.get(_DRIVER_ID_KEY, chat_id)
    plan_id: str | None = context.chat_data.get(_ACTIVE_PLAN_KEY)

    logger.info(
        "Text from driver_id=%s chat=%s plan_id=%s text=%r",
        driver_id, chat_id, plan_id, text[:100],
    )

    if plan_id is None:
        logger.info("No active plan for chat_id=%s; ignoring text message.", chat_id)
        return

    is_ack = bool(_ACK_PATTERNS.search(text))
    received_at = datetime.now(timezone.utc).isoformat()

    payload: dict[str, Any] = {
        "plan_id": plan_id,
        "driver_id": driver_id,
        "acknowledged": is_ack,
        "received_at": received_at,
        "message": text[:500],
    }

    logger.info(
        "Recording acknowledgement: driver_id=%s  plan_id=%s  ack=%s",
        driver_id, plan_id, is_ack,
    )

    try:
        resp = await _post(f"/api/v1/plans/{plan_id}/acknowledgements", payload)
        if resp.status_code in (200, 201):
            logger.info(
                "Acknowledgement recorded: driver_id=%s plan_id=%s ack=%s",
                driver_id, plan_id, is_ack,
            )
        elif resp.status_code == 409:
            logger.warning(
                "Idempotency conflict on acknowledgement: driver_id=%s plan_id=%s",
                driver_id, plan_id,
            )
        else:
            logger.error(
                "API error on acknowledgement: status=%s body=%s",
                resp.status_code, resp.text[:500],
            )
    except httpx.TimeoutException:
        logger.error("Timeout posting acknowledgement for plan_id=%s", plan_id)
    except httpx.RequestError as exc:
        logger.error("Network error posting acknowledgement for plan_id=%s: %s", plan_id, exc)


# ---------------------------------------------------------------------------
# OUTBOUND DISPATCHER — called by the FastAPI backend
# ---------------------------------------------------------------------------

async def send_dispatch_message(
    *,
    chat_id: str | int,
    driver_id: str,
    plan_id: str,
    message: str,
    bot: Bot | None = None,
    application: Application | None = None,
) -> str:
    """
    Send a dispatch instruction to a driver over Telegram.

    Called by the FastAPI /api/v1/plans/{plan_id}/dispatch endpoint (via the
    app's lifespan-managed bot instance).  Returns the Telegram message_id as
    a string so the API can store it as provider_message_id in DispatchResult.

    Strictly tracks "message SENT" state only — driver acknowledgement is a
    separate event handled by handle_text_message.

    Parameters
    ----------
    chat_id     : Telegram chat / user ID for the driver.
    driver_id   : Internal driver identifier.
    plan_id     : The plan being dispatched — stored in chat_data for later ack.
    message     : Human-readable dispatch instructions.
    bot         : An already-authenticated Bot instance (preferred).
    application : Fall back to application.bot if bot is None.

    Returns
    -------
    str — Telegram message_id (as string) on success.

    Raises
    ------
    TelegramError    if the message could not be delivered.
    ValueError       if neither bot nor application is provided.
    """
    if bot is None:
        if application is None:
            raise ValueError("Either 'bot' or 'application' must be supplied.")
        bot = application.bot

    try:
        sent: Message = await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="HTML",
        )
    except BadRequest as exc:
        logger.error(
            "Telegram BadRequest sending to chat_id=%s plan_id=%s: %s",
            chat_id, plan_id, exc,
        )
        raise
    except TimedOut as exc:
        logger.error(
            "Telegram TimedOut sending to chat_id=%s plan_id=%s: %s",
            chat_id, plan_id, exc,
        )
        raise
    except NetworkError as exc:
        logger.error(
            "Telegram NetworkError sending to chat_id=%s plan_id=%s: %s",
            chat_id, plan_id, exc,
        )
        raise
    except TelegramError as exc:
        logger.error(
            "TelegramError sending to chat_id=%s plan_id=%s: %s",
            chat_id, plan_id, exc,
        )
        raise

    provider_message_id = str(sent.message_id)

    # Persist plan_id in chat_data so subsequent text replies from this chat
    # are correctly associated with this plan for acknowledgement tracking.
    # NOTE: chat_data is only available when using the Application context.
    if application is not None:
        chat_data = application.chat_data.setdefault(int(chat_id), {})
        chat_data[_ACTIVE_PLAN_KEY] = plan_id
        chat_data[_DRIVER_ID_KEY] = driver_id

    logger.info(
        "Dispatch message SENT: plan_id=%s driver_id=%s chat_id=%s telegram_message_id=%s",
        plan_id, driver_id, chat_id, provider_message_id,
    )

    # IMPORTANT: Returning here marks SENT state only.
    # Driver ACKNOWLEDGED is a separate state, recorded only when the driver
    # replies and handle_text_message processes the DriverAcknowledgement.
    return provider_message_id


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log all unhandled Telegram errors without crashing the polling loop."""
    logger.error(
        "Unhandled exception in update handler: %s",
        context.error,
        exc_info=context.error,
    )


# ---------------------------------------------------------------------------
# Application factory — importable by FastAPI lifespan
# ---------------------------------------------------------------------------

def build_application(token: str | None = None) -> Application:
    """
    Construct and configure the python-telegram-bot Application.

    Returns the Application object; call `.run_polling()` or `.run_webhook()`
    on the returned object from your entry point, or use `async with app` in
    a FastAPI lifespan to share the Bot instance with the HTTP handlers.
    """
    bot_token = token or TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is not set. Set it in .env or pass token to build_application()."
        )

    app: Application = (
        ApplicationBuilder()
        .token(bot_token)
        .build()
    )

    # Handler: live or static location shares
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))

    # Handler: text replies (acknowledgements, free-form messages)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Catch-all error handler
    app.add_error_handler(error_handler)

    logger.info("ReliefRoute Telegram bot application built and handlers registered.")
    return app


# ---------------------------------------------------------------------------
# Entry point (polling mode — suitable for hackathon / local demo)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting ReliefRoute Telegram bot (polling mode)...")
    application = build_application()
    application.run_polling(
        allowed_updates=["message", "edited_message"],
        drop_pending_updates=True,
    )
