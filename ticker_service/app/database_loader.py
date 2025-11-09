"""
Database loader for Kite trading accounts.

This module loads KiteConnect credentials from the ticker_service's own database.
Architecture: Ticker service owns credentials, user service owns access control.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List

from sqlalchemy import create_engine, Column, String, Boolean, Text, TIMESTAMP, LargeBinary
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from loguru import logger

from .config import get_settings
from .crypto import get_encryption


class Base(DeclarativeBase):
    pass


class KiteAccountDB(Base):
    """
    SQLAlchemy model for kite_accounts table.

    This table stores encrypted KiteConnect credentials in the ticker_service database.
    Ownership: Ticker service owns this table and manages credentials.
    """
    __tablename__ = 'kite_accounts'

    account_id = Column(String(50), primary_key=True)
    broker = Column(String(50), nullable=False, default='kite')
    broker_user_id = Column(String(100), nullable=False, unique=True)
    nickname = Column(String(255), nullable=False)
    account_name = Column(String(255))

    # Encrypted credentials (base64 for dev, KMS for production)
    api_key_encrypted = Column(Text, nullable=False)
    api_secret_encrypted = Column(Text)
    access_token_encrypted = Column(Text)
    password_encrypted = Column(Text)
    totp_secret_encrypted = Column(Text)

    # Subscription tier filtering
    subscription_tier = Column(String(20), nullable=False, default='unknown')
    market_data_available = Column(Boolean, nullable=False, default=False)
    subscription_tier_last_checked = Column(TIMESTAMP)

    # Status
    status = Column(String(20), nullable=False, default='active')
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False)
    updated_at = Column(TIMESTAMP, nullable=False)
    last_used_at = Column(TIMESTAMP)

    # Additional fields
    token_dir = Column(Text)


def _decrypt_credential(encrypted_value: str | bytes | None) -> str | None:
    """
    Decrypt a credential value using AES-256-GCM.

    Args:
        encrypted_value: Encrypted credential (bytes) or base64 string (legacy)

    Returns:
        Decrypted credential or None if input is None/empty
    """
    if not encrypted_value:
        return None

    try:
        # Handle both bytes (new format) and str (legacy base64)
        if isinstance(encrypted_value, str):
            # Legacy base64 format - convert to bytes for migration
            import base64
            encrypted_value = base64.b64decode(encrypted_value)

        # Decrypt using AES-256-GCM
        encryptor = get_encryption()
        return encryptor.decrypt(encrypted_value)
    except Exception as exc:
        logger.error("Failed to decrypt credential: %s", exc)
        return None


def load_accounts_from_database() -> Dict[str, Dict[str, Any]]:
    """
    Load KiteConnect accounts from ticker_service database.

    Filters accounts by:
    - is_active = True
    - market_data_available = True (excludes Personal tier accounts)

    Returns:
        Dict mapping account_id to account credentials dict with keys:
        - api_key: Decrypted API key
        - api_secret: Decrypted API secret
        - access_token: Decrypted access token (if available)
        - username: Broker user ID (e.g., 'XJ4540')
        - password: Decrypted password
        - totp_key: Decrypted TOTP secret
        - token_dir: Token directory path
        - subscription_tier: Tier name (connect, startup, personal)
        - market_data_available: Boolean flag
    """
    settings = get_settings()

    # Build database URL from settings
    database_url = (
        f"postgresql://{settings.instrument_db_user}:{settings.instrument_db_password}"
        f"@{settings.instrument_db_host}:{settings.instrument_db_port}/{settings.instrument_db_name}"
    )

    logger.debug("Connecting to database to load Kite accounts: %s@%s/%s",
                settings.instrument_db_user,
                settings.instrument_db_host,
                settings.instrument_db_name)

    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Query active accounts with market data access
        accounts_query = session.query(KiteAccountDB).filter(
            KiteAccountDB.is_active == True,
            KiteAccountDB.market_data_available == True
        )

        db_accounts = accounts_query.all()

        if not db_accounts:
            logger.warning("No active accounts with market data access found in database")
            return {}

        logger.info("Found %d active account(s) with market data access in database", len(db_accounts))

        # Decrypt credentials and build result dict
        kite_accounts: Dict[str, Dict[str, Any]] = {}
        for db_account in db_accounts:
            account_id = db_account.account_id

            # Decrypt credentials
            api_key = _decrypt_credential(db_account.api_key_encrypted)
            api_secret = _decrypt_credential(db_account.api_secret_encrypted)
            access_token = _decrypt_credential(db_account.access_token_encrypted)
            password = _decrypt_credential(db_account.password_encrypted)
            totp_key = _decrypt_credential(db_account.totp_secret_encrypted)

            if not api_key:
                logger.warning("Skipping account %s: missing or invalid API key", account_id)
                continue

            # Determine token directory
            token_dir = None
            if db_account.token_dir:
                token_dir = Path(db_account.token_dir)
            else:
                # Default: use account_id for token filename
                token_dir = Path(__file__).parent / "kite" / "tokens"

            kite_accounts[account_id] = {
                'api_key': api_key,
                'api_secret': api_secret,
                'access_token': access_token,
                'username': db_account.broker_user_id,
                'password': password,
                'totp_key': totp_key,
                'token_dir': str(token_dir),
                'subscription_tier': db_account.subscription_tier,
                'market_data_available': db_account.market_data_available,
                'nickname': db_account.nickname,
            }

            logger.info(
                "Loaded account %s (%s): tier=%s, broker_user_id=%s, market_data=True",
                account_id,
                db_account.nickname,
                db_account.subscription_tier,
                db_account.broker_user_id
            )

        # Log filtering results before closing session
        all_accounts_query = session.query(KiteAccountDB).filter(KiteAccountDB.is_active == True)
        all_active = all_accounts_query.count()
        excluded_count = all_active - len(kite_accounts)

        if excluded_count > 0:
            logger.warning(
                "Excluded %d active account(s) without market data access (Personal tier)",
                excluded_count
            )

        session.close()

        return kite_accounts

    except Exception as exc:
        logger.exception("Failed to load accounts from database: %s", exc)
        return {}


def check_database_connection() -> bool:
    """
    Check if database connection is available.

    Returns:
        True if connection successful, False otherwise
    """
    settings = get_settings()
    database_url = (
        f"postgresql://{settings.instrument_db_user}:{settings.instrument_db_password}"
        f"@{settings.instrument_db_host}:{settings.instrument_db_port}/{settings.instrument_db_name}"
    )

    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        logger.debug("Database connection check successful")
        return True
    except Exception as exc:
        logger.warning(f"Database connection check failed: {exc}")
        return False
