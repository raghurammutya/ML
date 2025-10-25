from __future__ import annotations

import asyncio
import random
import time
from typing import List

from loguru import logger

from .config import get_settings
from .schema import Instrument, OptionSnapshot
from .publisher import publish_option_snapshot, publish_underlying_bar

settings = get_settings()


def _mock_option_instruments() -> List[Instrument]:
    instruments = []
    strikes = [20000 + 100 * i for i in range(-settings.otm_levels, settings.otm_levels + 1)]
    for expiry_offset in range(settings.option_expiry_window):
        expiry = f"2025-11-{7 + expiry_offset * 7:02d}"
        for idx, strike in enumerate(strikes):
            option_type = 'CE' if idx >= 0 else 'PE'
            instruments.append(
                Instrument(
                    symbol=settings.fo_underlying,
                    instrument_token=1_000_000 + idx + expiry_offset * 1000,
                    strike=strike,
                    expiry=expiry,
                    instrument_type=option_type,
                )
            )
    return instruments


async def mock_stream_loop() -> None:
    instruments = _mock_option_instruments()
    logger.info("Starting mock ticker loop for %d instruments", len(instruments))
    while True:
        ts = int(time.time())
        # publish underlying bar
        await publish_underlying_bar({
            "symbol": settings.fo_underlying,
            "open": random.uniform(24000, 25000),
            "high": random.uniform(25000, 25500),
            "low": random.uniform(23500, 24500),
            "close": random.uniform(24000, 25000),
            "volume": random.randint(100_000, 300_000),
            "ts": ts,
        })

        # publish option snapshots
        for instrument in instruments:
            snapshot = OptionSnapshot(
                instrument=instrument,
                last_price=random.uniform(10, 300),
                volume=random.randint(100, 5000),
                iv=random.uniform(0.1, 0.4),
                delta=random.uniform(-1, 1),
                gamma=random.uniform(0, 0.1),
                theta=random.uniform(-10, 0),
                vega=random.uniform(0, 10),
                timestamp=ts,
            )
            await publish_option_snapshot(snapshot)
        await asyncio.sleep(1)
