from __future__ import annotations

import datetime as dt
import logging
import warnings

from livekit import api
from jwt.warnings import InsecureKeyLengthWarning

from app.config.settings import Settings

logger = logging.getLogger(__name__)

MIN_RECOMMENDED_SECRET_LENGTH = 32
_weak_secret_warning_emitted = False


def build_livekit_access_token(
    settings: Settings,
    *,
    room_name: str,
    identity: str,
    hidden: bool = False,
    agent: bool = False,
    ttl_hours: int = 12,
) -> str:
    global _weak_secret_warning_emitted
    if len(settings.livekit_api_secret) < MIN_RECOMMENDED_SECRET_LENGTH:
        if not _weak_secret_warning_emitted:
            logger.warning(
                "LIVEKIT_API_SECRET is shorter than the recommended %s characters. "
                "Local dev may still work, but use a longer random secret for stable JWT hygiene.",
                MIN_RECOMMENDED_SECRET_LENGTH,
            )
            _weak_secret_warning_emitted = True
    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
        hidden=hidden or None,
        agent=agent or None,
    )
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grants)
        .with_ttl(dt.timedelta(hours=ttl_hours))
    )
    if agent:
        token = token.with_kind("agent")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=InsecureKeyLengthWarning)
        return token.to_jwt()
