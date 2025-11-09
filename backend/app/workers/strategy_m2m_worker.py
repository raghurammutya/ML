"""
Strategy M2M Background Worker

Calculates and stores minute-wise Mark-to-Market (M2M) for all active strategies.

Formula:
    For each instrument in strategy:
        M2M_contribution = LTP × Quantity × Direction_Multiplier
        where Direction_Multiplier = -1 for BUY (cash outflow)
                                   = +1 for SELL (cash inflow)

    Strategy_M2M = Σ(M2M_contribution for all instruments)

Example:
    Iron Condor Strategy:
        - BUY  NIFTY 24500 CE: qty=50, ltp=120 → -6,000
        - SELL NIFTY 24600 CE: qty=50, ltp=130 → +6,500
        - BUY  NIFTY 24800 CE: qty=50, ltp=40  → -2,000
        Total M2M = -6,000 + 6,500 - 2,000 = -1,500 (loss of ₹1,500)

Runs: Every minute
Stores: OHLC candles in strategy_m2m_candles table

Phase 2.5 Day 2
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import aiohttp

logger = logging.getLogger(__name__)


class StrategyM2MWorker:
    """
    Background worker that calculates M2M for all active strategies.
    """

    def __init__(self, db_pool, redis_client, ticker_service_url: str):
        """
        Initialize the M2M worker.

        Args:
            db_pool: AsyncPG connection pool
            redis_client: Async Redis client
            ticker_service_url: URL of ticker service for fallback LTP fetching
        """
        self.db = db_pool
        self.redis = redis_client
        self.ticker_url = ticker_service_url
        self.running = False
        self.iteration_count = 0

    async def start(self):
        """Start the M2M calculation loop."""
        self.running = True
        logger.info("[StrategyM2MWorker] Starting M2M calculation worker")

        while self.running:
            try:
                await self.calculate_all_strategies()
                self.iteration_count += 1

                # Wait 60 seconds before next iteration
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"[StrategyM2MWorker] Error in M2M calculation loop: {e}", exc_info=True)
                # Wait 10 seconds before retry on error
                await asyncio.sleep(10)

    async def stop(self):
        """Stop the M2M calculation loop."""
        logger.info("[StrategyM2MWorker] Stopping M2M calculation worker")
        self.running = False

    async def calculate_all_strategies(self):
        """
        Calculate M2M for all active strategies.

        This is the main function that runs every minute.
        """
        timestamp = datetime.utcnow().replace(second=0, microsecond=0)

        logger.debug(f"[StrategyM2MWorker] Starting M2M calculation at {timestamp}")

        try:
            async with self.db.acquire() as conn:
                # Get all active strategies
                strategies = await conn.fetch("""
                    SELECT strategy_id, trading_account_id, strategy_name
                    FROM strategy
                    WHERE status = 'active' AND is_active = TRUE
                """)

                if not strategies:
                    logger.debug("[StrategyM2MWorker] No active strategies found")
                    return

                logger.info(f"[StrategyM2MWorker] Calculating M2M for {len(strategies)} strategies")

                # Calculate M2M for each strategy
                for strategy in strategies:
                    try:
                        await self.calculate_strategy_m2m(
                            strategy_id=strategy['strategy_id'],
                            strategy_name=strategy['strategy_name'],
                            trading_account_id=strategy['trading_account_id'],
                            timestamp=timestamp
                        )
                    except Exception as e:
                        logger.error(
                            f"[StrategyM2MWorker] Failed to calculate M2M for strategy {strategy['strategy_id']}: {e}",
                            exc_info=True
                        )

        except Exception as e:
            logger.error(f"[StrategyM2MWorker] Failed to fetch active strategies: {e}", exc_info=True)

    async def calculate_strategy_m2m(
        self,
        strategy_id: int,
        strategy_name: str,
        trading_account_id: str,
        timestamp: datetime
    ):
        """
        Calculate M2M for a single strategy.

        Args:
            strategy_id: Strategy ID
            strategy_name: Strategy name (for logging)
            trading_account_id: Trading account ID
            timestamp: Current timestamp (minute precision)
        """
        async with self.db.acquire() as conn:
            # Get all instruments in this strategy
            instruments = await conn.fetch("""
                SELECT
                    tradingsymbol,
                    exchange,
                    instrument_token,
                    direction,
                    quantity,
                    entry_price,
                    lot_size
                FROM strategy_instruments
                WHERE strategy_id = $1
            """, strategy_id)

            if not instruments:
                logger.debug(f"[StrategyM2MWorker] Strategy {strategy_id} has no instruments")
                return

            # Fetch LTPs for all instruments
            symbols_to_fetch = [
                (inst['tradingsymbol'], inst['exchange'], inst['instrument_token'])
                for inst in instruments
            ]

            ltps = await self.fetch_ltps(symbols_to_fetch)

            # Calculate M2M for each instrument
            m2m_contributions = []
            missing_ltps = []

            for inst in instruments:
                symbol = inst['tradingsymbol']
                ltp = ltps.get(symbol)

                if ltp is None:
                    missing_ltps.append(symbol)
                    logger.warning(
                        f"[StrategyM2MWorker] No LTP for {symbol} in strategy {strategy_id}, skipping"
                    )
                    continue

                # Direction multiplier: BUY = -1 (paid money), SELL = +1 (received money)
                direction_multiplier = -1 if inst['direction'] == 'BUY' else 1

                # Calculate M2M contribution
                # M2M = (LTP - Entry_Price) × Quantity × Lot_Size × Direction
                lot_size = inst['lot_size'] or 1
                quantity = inst['quantity']
                entry_price = inst['entry_price']

                # Current value and entry value
                current_value = Decimal(str(ltp)) * quantity * lot_size
                entry_value = entry_price * quantity * lot_size

                # M2M = direction × (current - entry)
                # For BUY: we paid entry_value, current value is what we have
                #          M2M = -(current_value - entry_value) if we sold at current
                #          But actually: M2M = current - entry (profit if current > entry)
                #                       With direction: BUY needs to show loss as -ve
                #
                # Actually simpler:
                # BUY: We spent entry_value, now worth current_value
                #      P&L = current - entry (positive if price went up)
                # SELL: We received entry_value, now owe current_value
                #      P&L = entry - current (positive if price went down)

                if inst['direction'] == 'BUY':
                    m2m_contribution = current_value - entry_value
                else:  # SELL
                    m2m_contribution = entry_value - current_value

                m2m_contributions.append(m2m_contribution)

                # Update current_price and current_pnl in strategy_instruments
                await conn.execute("""
                    UPDATE strategy_instruments
                    SET current_price = $1,
                        current_pnl = $2,
                        updated_at = NOW()
                    WHERE strategy_id = $3
                      AND tradingsymbol = $4
                      AND exchange = $5
                """, Decimal(str(ltp)), m2m_contribution, strategy_id, symbol, inst['exchange'])

            if not m2m_contributions:
                logger.warning(
                    f"[StrategyM2MWorker] Strategy {strategy_id} has no valid M2M contributions "
                    f"(missing LTPs: {missing_ltps})"
                )
                return

            # Total strategy M2M
            total_m2m = sum(m2m_contributions)

            logger.debug(
                f"[StrategyM2MWorker] Strategy {strategy_id} ({strategy_name}): "
                f"M2M = ₹{total_m2m:,.2f} from {len(m2m_contributions)} instruments"
            )

            # Store M2M candle
            # For now, since we calculate once per minute, OHLC are all the same
            # In a real-time system, you'd track min/max during the minute
            await self.store_m2m_candle(
                conn=conn,
                strategy_id=strategy_id,
                timestamp=timestamp,
                open_m2m=total_m2m,
                high_m2m=total_m2m,
                low_m2m=total_m2m,
                close_m2m=total_m2m,
                instrument_count=len(instruments)
            )

            # Update strategy current_m2m and total_pnl
            await conn.execute("""
                UPDATE strategy
                SET current_m2m = $1,
                    total_pnl = $2,
                    updated_at = NOW()
                WHERE strategy_id = $3
            """, total_m2m, total_m2m, strategy_id)

    async def fetch_ltps(
        self,
        symbols: List[Tuple[str, str, Optional[int]]]
    ) -> Dict[str, float]:
        """
        Fetch Last Traded Prices (LTPs) for multiple symbols.

        Tries Redis cache first, falls back to Ticker Service HTTP API.

        Args:
            symbols: List of (tradingsymbol, exchange, instrument_token) tuples

        Returns:
            Dictionary mapping tradingsymbol to LTP
        """
        ltps = {}

        # Try Redis cache first (fast path)
        for tradingsymbol, exchange, instrument_token in symbols:
            try:
                # Try multiple cache keys
                cache_keys = [
                    f"ltp:{exchange}:{tradingsymbol}",
                    f"ticker:{instrument_token}:ltp" if instrument_token else None,
                ]

                for cache_key in cache_keys:
                    if not cache_key:
                        continue

                    cached_ltp = await self.redis.get(cache_key)
                    if cached_ltp:
                        ltps[tradingsymbol] = float(cached_ltp)
                        break

            except Exception as e:
                logger.debug(f"[StrategyM2MWorker] Redis fetch failed for {tradingsymbol}: {e}")

        # If we got all LTPs from cache, return early
        if len(ltps) == len(symbols):
            logger.debug(f"[StrategyM2MWorker] All {len(ltps)} LTPs fetched from Redis cache")
            return ltps

        # Fetch missing LTPs from Ticker Service (slow path)
        missing_symbols = [
            (ts, ex, it) for ts, ex, it in symbols if ts not in ltps
        ]

        if missing_symbols:
            logger.debug(
                f"[StrategyM2MWorker] Fetching {len(missing_symbols)} LTPs from Ticker Service"
            )

            ticker_ltps = await self.fetch_ltps_from_ticker_service(missing_symbols)
            ltps.update(ticker_ltps)

        return ltps

    async def fetch_ltps_from_ticker_service(
        self,
        symbols: List[Tuple[str, str, Optional[int]]]
    ) -> Dict[str, float]:
        """
        Fetch LTPs from Ticker Service HTTP API.

        Args:
            symbols: List of (tradingsymbol, exchange, instrument_token) tuples

        Returns:
            Dictionary mapping tradingsymbol to LTP
        """
        ltps = {}

        # For now, we'll fetch them one by one
        # TODO: Implement batch fetching endpoint in ticker service
        async with aiohttp.ClientSession() as session:
            for tradingsymbol, exchange, instrument_token in symbols:
                try:
                    # Try to fetch quote from ticker service
                    url = f"{self.ticker_url}/quote/{exchange}/{tradingsymbol}"

                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status == 200:
                            data = await response.json()
                            ltp = data.get('last_price') or data.get('ltp')
                            if ltp:
                                ltps[tradingsymbol] = float(ltp)
                        else:
                            logger.warning(
                                f"[StrategyM2MWorker] Ticker service returned {response.status} "
                                f"for {tradingsymbol}"
                            )

                except asyncio.TimeoutError:
                    logger.warning(f"[StrategyM2MWorker] Timeout fetching LTP for {tradingsymbol}")
                except Exception as e:
                    logger.warning(f"[StrategyM2MWorker] Failed to fetch LTP for {tradingsymbol}: {e}")

        return ltps

    async def store_m2m_candle(
        self,
        conn,
        strategy_id: int,
        timestamp: datetime,
        open_m2m: Decimal,
        high_m2m: Decimal,
        low_m2m: Decimal,
        close_m2m: Decimal,
        instrument_count: int
    ):
        """
        Store M2M candle in database.

        Uses ON CONFLICT to update if candle already exists for this timestamp.

        Args:
            conn: Database connection
            strategy_id: Strategy ID
            timestamp: Candle timestamp (minute precision)
            open_m2m: Open M2M
            high_m2m: High M2M
            low_m2m: Low M2M
            close_m2m: Close M2M
            instrument_count: Number of instruments in strategy
        """
        try:
            await conn.execute("""
                INSERT INTO strategy_m2m_candles
                (strategy_id, timestamp, open, high, low, close, instrument_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (timestamp, strategy_id) DO UPDATE
                SET open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    instrument_count = EXCLUDED.instrument_count
            """, strategy_id, timestamp, open_m2m, high_m2m, low_m2m, close_m2m, instrument_count)

            logger.debug(
                f"[StrategyM2MWorker] Stored M2M candle for strategy {strategy_id} "
                f"at {timestamp}: ₹{close_m2m:,.2f}"
            )

        except Exception as e:
            logger.error(
                f"[StrategyM2MWorker] Failed to store M2M candle for strategy {strategy_id}: {e}",
                exc_info=True
            )
            raise


async def strategy_m2m_task(db_pool, redis_client, ticker_service_url: str):
    """
    Task function for strategy M2M calculation.

    This function is called by the task supervisor in main.py.

    Args:
        db_pool: AsyncPG connection pool
        redis_client: Async Redis client
        ticker_service_url: URL of ticker service
    """
    worker = StrategyM2MWorker(db_pool, redis_client, ticker_service_url)

    try:
        await worker.start()
    except asyncio.CancelledError:
        logger.info("[StrategyM2MWorker] Task cancelled, stopping worker")
        await worker.stop()
        raise
    except Exception as e:
        logger.error(f"[StrategyM2MWorker] Worker crashed: {e}", exc_info=True)
        raise
