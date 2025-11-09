"""
Detect subscription tiers for all existing trading accounts.

Run this after migration to populate tier info for existing accounts.

Usage:
    cd /home/stocksadmin/Quantagro/tradingview-viz/user_service
    python scripts/detect_all_subscription_tiers.py

Or inside Docker container:
    docker exec tv-user-service python scripts/detect_all_subscription_tiers.py
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.redis_client import RedisClient
from app.models.trading_account import TradingAccount, TradingAccountStatus
from app.services.trading_account_service import TradingAccountService
from app.services.subscription_tier_detector import SubscriptionTierDetector
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def detect_all_tiers():
    """Detect subscription tier for all active trading accounts"""
    db: Session = SessionLocal()
    redis = RedisClient()
    await redis.connect()

    service = TradingAccountService(db, redis)

    try:
        # Get all active trading accounts
        accounts = db.query(TradingAccount).filter(
            TradingAccount.status == TradingAccountStatus.ACTIVE
        ).all()

        logger.info(f"Found {len(accounts)} active trading accounts")

        if len(accounts) == 0:
            logger.warning("No active trading accounts found. Nothing to do.")
            return

        results = {
            "total": len(accounts),
            "success": 0,
            "failed": 0,
            "connect": 0,
            "personal": 0,
            "startup": 0,
            "unknown": 0,
            "errors": []
        }

        for i, account in enumerate(accounts, 1):
            try:
                logger.info(
                    f"[{i}/{len(accounts)}] Detecting tier for account {account.trading_account_id} "
                    f"({account.broker}:{account.broker_user_id})..."
                )

                result = await service.detect_subscription_tier(
                    account.trading_account_id,
                    force_refresh=True
                )

                tier = result["subscription_tier"]
                market_data = result["market_data_available"]

                logger.info(f"  → Detected: {tier} (market_data={market_data})")

                results["success"] += 1
                results[tier] = results.get(tier, 0) + 1

            except Exception as e:
                logger.error(f"  → Error: {str(e)}")
                results["failed"] += 1
                results["errors"].append({
                    "account_id": account.trading_account_id,
                    "broker_user_id": account.broker_user_id,
                    "error": str(e)
                })

        # Print summary
        logger.info("\n" + "="*60)
        logger.info("DETECTION SUMMARY")
        logger.info("="*60)
        logger.info(f"Total accounts: {results['total']}")
        logger.info(f"Successful: {results['success']}")
        logger.info(f"Failed: {results['failed']}")
        logger.info(f"\nTier breakdown:")
        logger.info(f"  - Connect (paid, Rs. 500/month): {results['connect']}")
        logger.info(f"  - Personal (free, no market data): {results['personal']}")
        logger.info(f"  - Startup (free, full features): {results['startup']}")
        logger.info(f"  - Unknown: {results['unknown']}")

        if results["errors"]:
            logger.warning(f"\n⚠️  Errors encountered:")
            for err in results["errors"]:
                logger.warning(f"  - Account {err['account_id']} ({err['broker_user_id']}): {err['error']}")
        else:
            logger.info("\n✅ All accounts processed successfully!")

        # Print market data summary
        total_with_market_data = results['connect'] + results['startup']
        logger.info(f"\nMarket Data Availability:")
        logger.info(f"  - Accounts WITH market data: {total_with_market_data}")
        logger.info(f"  - Accounts WITHOUT market data: {results['personal']}")

        if total_with_market_data > 0:
            logger.info(f"\n📊 {total_with_market_data} account(s) can be used for WebSocket subscriptions")

        return results

    finally:
        await redis.close()
        db.close()


if __name__ == "__main__":
    logger.info("Starting subscription tier detection for all accounts...")
    asyncio.run(detect_all_tiers())
    logger.info("Done!")
