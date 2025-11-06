"""
Historical Greeks Calculator

Calculates option Greeks for historical candle data by:
1. Fetching underlying prices from database
2. Falling back to Kite API if data not in database
3. Matching option candles with underlying prices by timestamp
4. Computing Greeks using GreeksCalculator
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from loguru import logger

from .config import get_settings
from .greeks_calculator import GreeksCalculator
from .instrument_registry import Instrument

settings = get_settings()
IST_TZ = ZoneInfo("Asia/Kolkata")


class HistoricalGreeksEnricher:
    """Enriches historical option candles with Greeks"""

    def __init__(self, db_pool, kite_fetch_fn):
        """
        Args:
            db_pool: AsyncConnectionPool for database access
            kite_fetch_fn: Async function to fetch history from Kite
                          signature: async (instrument_token, from_ts, to_ts, interval, oi) -> List[dict]
        """
        self._db_pool = db_pool
        self._kite_fetch = kite_fetch_fn
        self._greeks_calc = GreeksCalculator(
            interest_rate=0.10,
            dividend_yield=0.0,
            expiry_time_hour=15,
            expiry_time_minute=30,
            market_timezone="Asia/Kolkata"
        )

    async def enrich_option_candles(
        self,
        option_metadata: Instrument,
        option_candles: List[dict],
        from_ts: int,
        to_ts: int,
        interval: str = "minute"
    ) -> List[dict]:
        """
        Enrich option candles with Greeks.

        Args:
            option_metadata: Instrument metadata for the option
            option_candles: List of option OHLC candles from Kite
            from_ts: Start timestamp (epoch)
            to_ts: End timestamp (epoch)
            interval: Interval string (e.g., "minute")

        Returns:
            Option candles enriched with iv, delta, gamma, theta, vega, underlying
        """
        # Check if this is an option instrument
        if not self._is_option(option_metadata):
            logger.debug(f"Instrument {option_metadata.tradingsymbol} is not an option, skipping Greeks")
            return option_candles

        # Get underlying instrument token
        underlying_token = self._get_underlying_token(option_metadata)
        if not underlying_token:
            logger.warning(f"Could not determine underlying for {option_metadata.tradingsymbol}")
            return option_candles

        # Fetch underlying prices
        underlying_map = await self._fetch_underlying_prices(
            underlying_token,
            option_metadata.name or "NIFTY 50",
            from_ts,
            to_ts,
            interval
        )

        if not underlying_map:
            logger.warning(f"No underlying data available for {option_metadata.tradingsymbol}")
            return option_candles

        # Enrich each candle with Greeks
        enriched = []
        for candle in option_candles:
            enriched_candle = self._calculate_greeks_for_candle(
                candle,
                option_metadata,
                underlying_map
            )
            enriched.append(enriched_candle)

        logger.info(
            f"Enriched {len(enriched)} candles with Greeks for {option_metadata.tradingsymbol}"
        )
        return enriched

    def _is_option(self, metadata: Instrument) -> bool:
        """Check if instrument is an option"""
        return metadata.segment in ("NFO-OPT", "BFO-OPT", "MCX-OPT") or \
               metadata.instrument_type in ("CE", "PE")

    def _get_underlying_token(self, option_metadata: Instrument) -> Optional[int]:
        """Extract underlying instrument token from option metadata"""
        # Try exchange_token field (common for derivatives)
        if hasattr(option_metadata, 'exchange_token') and option_metadata.exchange_token:
            # For now, return None - we'll use the name to look up
            pass

        # For NIFTY options, the underlying is "NIFTY 50" index
        name = option_metadata.name or ""
        if "NIFTY" in name.upper():
            # NIFTY 50 index token is typically 256265
            return 256265
        elif "BANKNIFTY" in name.upper():
            # BANKNIFTY index token
            return 260105
        elif "FINNIFTY" in name.upper():
            return 257801
        elif "MIDCPNIFTY" in name.upper():
            return 288009

        logger.warning(f"Unknown underlying for {option_metadata.tradingsymbol}")
        return None

    async def _fetch_underlying_prices(
        self,
        underlying_token: int,
        symbol: str,
        from_ts: int,
        to_ts: int,
        interval: str
    ) -> Dict[datetime, float]:
        """
        Fetch underlying prices, trying database first, then Kite API.

        Returns:
            Dict mapping timestamp -> close price
        """
        # Convert epoch to datetime
        from_dt = datetime.fromtimestamp(from_ts, tz=timezone.utc)
        to_dt = datetime.fromtimestamp(to_ts, tz=timezone.utc)

        # Try database first
        db_prices = await self._fetch_from_database(symbol, from_dt, to_dt)

        # Check coverage
        coverage = self._check_coverage(db_prices, from_dt, to_dt, interval)

        if coverage >= 0.8:  # 80% coverage threshold
            logger.info(f"Using {len(db_prices)} underlying prices from database (coverage: {coverage:.1%})")
            return db_prices

        # Insufficient data in DB, fetch from Kite
        logger.info(f"Database coverage {coverage:.1%} insufficient, fetching from Kite API")
        try:
            kite_candles = await self._kite_fetch(
                underlying_token,
                from_ts,
                to_ts,
                interval,
                False  # oi=False for underlying
            )

            # Save to database
            await self._save_to_database(symbol, kite_candles)

            # Build map
            kite_prices = {}
            for candle in kite_candles:
                ts = self._parse_timestamp(candle.get("date"))
                close = float(candle.get("close") or 0)
                if ts and close > 0:
                    kite_prices[ts] = close

            logger.info(f"Fetched {len(kite_prices)} underlying prices from Kite API")
            return kite_prices

        except Exception as e:
            logger.error(f"Failed to fetch underlying from Kite: {e}")
            # Return whatever we have from database
            return db_prices

    async def _fetch_from_database(
        self,
        symbol: str,
        from_dt: datetime,
        to_dt: datetime
    ) -> Dict[datetime, float]:
        """Fetch underlying bars from minute_bars table"""
        try:
            # Convert to IST naive timestamps (as stored in DB)
            from_ist = from_dt.astimezone(IST_TZ).replace(tzinfo=None)
            to_ist = to_dt.astimezone(IST_TZ).replace(tzinfo=None)

            query = """
                SELECT time, close
                FROM minute_bars
                WHERE symbol = $1
                  AND resolution = 1
                  AND time >= $2
                  AND time <= $3
                ORDER BY time
            """

            async with self._db_pool.connection() as conn:
                rows = await conn.execute(query, (symbol, from_ist, to_ist))
                records = await rows.fetchall()

                prices = {}
                for row in records:
                    # Convert IST naive to UTC aware
                    time_ist = row[0]  # naive IST timestamp
                    close = float(row[1])

                    # Make IST aware then convert to UTC
                    time_aware = time_ist.replace(tzinfo=IST_TZ)
                    time_utc = time_aware.astimezone(timezone.utc)

                    prices[time_utc] = close

                return prices

        except Exception as e:
            logger.error(f"Database fetch failed for {symbol}: {e}")
            return {}

    async def _save_to_database(self, symbol: str, candles: List[dict]) -> None:
        """Save underlying candles to minute_bars table"""
        if not candles:
            return

        try:
            insert_sql = """
                INSERT INTO minute_bars (
                    time, symbol, resolution, open, high, low, close, volume, metadata
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9
                )
                ON CONFLICT (symbol, resolution, time)
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    metadata = EXCLUDED.metadata
            """

            async with self._db_pool.connection() as conn:
                for candle in candles:
                    ts = self._parse_timestamp(candle.get("date"))
                    if not ts:
                        continue

                    # Convert to IST naive (storage format)
                    time_ist = ts.astimezone(IST_TZ).replace(tzinfo=None)

                    await conn.execute(
                        insert_sql,
                        (
                            time_ist,
                            symbol,
                            1,  # resolution = 1 minute
                            float(candle.get("open") or 0),
                            float(candle.get("high") or 0),
                            float(candle.get("low") or 0),
                            float(candle.get("close") or 0),
                            int(candle.get("volume") or 0),
                            {"source": "kite_backfill", "timeframe": "1min"}
                        )
                    )

            logger.info(f"Saved {len(candles)} underlying candles to database for {symbol}")

        except Exception as e:
            logger.error(f"Failed to save underlying candles to database: {e}")

    def _check_coverage(
        self,
        prices: Dict[datetime, float],
        from_dt: datetime,
        to_dt: datetime,
        interval: str
    ) -> float:
        """Check what percentage of expected data points we have"""
        if not prices:
            return 0.0

        # Assume 1-minute intervals during market hours (9:15 AM - 3:30 PM IST)
        # That's 375 minutes per day
        expected_minutes = 0
        current = from_dt
        while current <= to_dt:
            current_ist = current.astimezone(IST_TZ)
            if current_ist.hour >= 9 and current_ist.hour < 16:
                # Rough estimate - count as market hours
                expected_minutes += 1
            current += timedelta(minutes=1)

        if expected_minutes == 0:
            return 0.0

        coverage = len(prices) / expected_minutes
        return min(coverage, 1.0)

    def _calculate_greeks_for_candle(
        self,
        candle: dict,
        option_metadata: Instrument,
        underlying_map: Dict[datetime, float]
    ) -> dict:
        """Calculate Greeks for a single candle"""
        # Parse timestamp
        ts = self._parse_timestamp(candle.get("date"))
        if not ts:
            logger.debug("Could not parse candle timestamp")
            return candle

        # Find nearest underlying price (within 5 minutes)
        underlying_price = self._find_nearest_price(ts, underlying_map, max_delta_minutes=5)
        if not underlying_price or underlying_price <= 0:
            logger.debug(f"No underlying price found for {ts}")
            # Return candle with null Greeks
            candle["iv"] = None
            candle["delta"] = None
            candle["gamma"] = None
            candle["theta"] = None
            candle["vega"] = None
            candle["underlying"] = None
            return candle

        # Get option parameters
        market_price = float(candle.get("close") or 0)
        strike = option_metadata.strike
        expiry = option_metadata.expiry
        option_type = option_metadata.instrument_type

        if not (market_price > 0 and strike and expiry and option_type in ("CE", "PE")):
            candle["iv"] = None
            candle["delta"] = None
            candle["gamma"] = None
            candle["theta"] = None
            candle["vega"] = None
            candle["underlying"] = underlying_price
            return candle

        # Calculate Greeks
        try:
            iv, greeks = self._greeks_calc.calculate_option_greeks(
                market_price=market_price,
                spot_price=underlying_price,
                strike_price=strike,
                expiry_date=expiry,
                option_type=option_type,
                current_time=ts
            )

            candle["iv"] = iv
            candle["delta"] = greeks.get("delta", 0.0)
            candle["gamma"] = greeks.get("gamma", 0.0)
            candle["theta"] = greeks.get("theta", 0.0)
            candle["vega"] = greeks.get("vega", 0.0)
            candle["underlying"] = underlying_price

        except Exception as e:
            logger.debug(f"Greeks calculation failed for {option_metadata.tradingsymbol} at {ts}: {e}")
            candle["iv"] = None
            candle["delta"] = None
            candle["gamma"] = None
            candle["theta"] = None
            candle["vega"] = None
            candle["underlying"] = underlying_price

        return candle

    def _find_nearest_price(
        self,
        target_ts: datetime,
        price_map: Dict[datetime, float],
        max_delta_minutes: int = 5
    ) -> Optional[float]:
        """Find the nearest underlying price within max_delta_minutes"""
        if not price_map:
            return None

        max_delta = timedelta(minutes=max_delta_minutes)
        nearest_ts = None
        nearest_delta = None

        for ts in price_map.keys():
            delta = abs(ts - target_ts)
            if delta <= max_delta:
                if nearest_delta is None or delta < nearest_delta:
                    nearest_delta = delta
                    nearest_ts = ts

        if nearest_ts:
            return price_map[nearest_ts]

        return None

    def _parse_timestamp(self, ts_value) -> Optional[datetime]:
        """Parse timestamp from various formats"""
        if isinstance(ts_value, datetime):
            if ts_value.tzinfo is None:
                ts_value = ts_value.replace(tzinfo=timezone.utc)
            return ts_value

        if isinstance(ts_value, str):
            try:
                dt = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass

        return None
