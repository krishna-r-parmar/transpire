import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx

from app.core.config import Settings
from app.domains.ideas.schemas import ExchangeRateRecord

_lock = asyncio.Lock()
_cached: tuple[datetime, ExchangeRateRecord] | None = None


class ExchangeRateUnavailableError(Exception):
    pass


async def get_inr_usd_rate(settings: Settings) -> ExchangeRateRecord:
    global _cached
    now = datetime.now(UTC)
    if _cached and now - _cached[0] < timedelta(minutes=settings.fx_cache_minutes):
        return _cached[1]
    async with _lock:
        if _cached and now - _cached[0] < timedelta(minutes=settings.fx_cache_minutes):
            return _cached[1]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.fx_api_base_url.rstrip('/')}/rate/INR/USD")
                response.raise_for_status()
                payload = response.json()
                record = ExchangeRateRecord(
                    rate=Decimal(str(payload["rate"])),
                    rate_date=date.fromisoformat(payload["date"]),
                )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ExchangeRateUnavailableError from error
        _cached = (now, record)
        return record
