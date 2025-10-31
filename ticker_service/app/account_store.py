"""
Database Persistence for Trading Accounts

Stores trading account credentials securely in PostgreSQL.
Supports CRUD operations and encryption of sensitive fields.
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime, timezone

from loguru import logger
import psycopg
from psycopg_pool import AsyncConnectionPool
from cryptography.fernet import Fernet
import os


class AccountStore:
    """PostgreSQL storage for trading accounts"""

    def __init__(self, connection_string: str, encryption_key: Optional[str] = None):
        self._pool: Optional[AsyncConnectionPool] = None
        self._connection_string = connection_string

        # Initialize encryption
        if encryption_key:
            self._cipher = Fernet(encryption_key.encode())
        else:
            # Generate a key if not provided (store this securely in production!)
            key = os.getenv("ACCOUNT_ENCRYPTION_KEY")
            if not key:
                logger.warning("No ACCOUNT_ENCRYPTION_KEY found, generating new key")
                key = Fernet.generate_key().decode()
                logger.warning(f"Generated encryption key: {key}")
                logger.warning("IMPORTANT: Store this key securely! Set ACCOUNT_ENCRYPTION_KEY environment variable.")
            self._cipher = Fernet(key.encode())

    def _encrypt(self, value: str) -> str:
        """Encrypt sensitive data"""
        if not value:
            return ""
        return self._cipher.encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        """Decrypt sensitive data"""
        if not value:
            return ""
        try:
            return self._cipher.decrypt(value.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt value: {e}")
            return ""

    async def initialize(self) -> None:
        """Initialize database connection pool and create table"""
        self._pool = AsyncConnectionPool(
            self._connection_string,
            min_size=2,
            max_size=10
        )

        # Create table if not exists
        async with self._pool.connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS trading_accounts (
                    account_id TEXT PRIMARY KEY,
                    api_key TEXT NOT NULL,
                    api_secret TEXT,
                    access_token TEXT,
                    username TEXT,
                    password TEXT,
                    totp_key TEXT,
                    token_dir TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    metadata JSONB
                )
            """)

            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trading_accounts_active
                ON trading_accounts(is_active) WHERE is_active = TRUE
            """)

        logger.info("Account store initialized")

    async def close(self) -> None:
        """Close database connection pool"""
        if self._pool:
            await self._pool.close()

    async def create(
        self,
        account_id: str,
        api_key: str,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        totp_key: Optional[str] = None,
        token_dir: Optional[str] = None,
        metadata: Optional[Dict] = None,
        max_retries: int = 3
    ) -> Dict:
        """Create a new trading account"""
        now = datetime.now(timezone.utc)

        # Encrypt sensitive fields
        encrypted_api_key = self._encrypt(api_key)
        encrypted_api_secret = self._encrypt(api_secret) if api_secret else None
        encrypted_access_token = self._encrypt(access_token) if access_token else None
        encrypted_password = self._encrypt(password) if password else None
        encrypted_totp_key = self._encrypt(totp_key) if totp_key else None

        for attempt in range(max_retries):
            try:
                async with self._pool.connection() as conn:
                    await conn.execute("""
                        INSERT INTO trading_accounts
                        (account_id, api_key, api_secret, access_token, username,
                         password, totp_key, token_dir, is_active, created_at, updated_at, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        account_id,
                        encrypted_api_key,
                        encrypted_api_secret,
                        encrypted_access_token,
                        username,
                        encrypted_password,
                        encrypted_totp_key,
                        token_dir,
                        True,
                        now,
                        now,
                        json.dumps(metadata) if metadata else None
                    ))

                logger.info(f"Created trading account: {account_id}")
                return await self.get(account_id)

            except psycopg.errors.UniqueViolation:
                raise ValueError(f"Account '{account_id}' already exists")
            except (psycopg.OperationalError, psycopg.InterfaceError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to create account after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Database error on attempt {attempt + 1}, retrying: {e}")
                await asyncio.sleep(2 ** attempt)

    async def get(self, account_id: str, decrypt: bool = True) -> Optional[Dict]:
        """Get a trading account by ID"""
        async with self._pool.connection() as conn:
            cursor = await conn.execute("""
                SELECT account_id, api_key, api_secret, access_token, username,
                       password, totp_key, token_dir, is_active, created_at, updated_at, metadata
                FROM trading_accounts
                WHERE account_id = %s
            """, (account_id,))

            row = await cursor.fetchone()
            if not row:
                return None

            account = {
                "account_id": row[0],
                "api_key": self._decrypt(row[1]) if decrypt else row[1],
                "api_secret": self._decrypt(row[2]) if (decrypt and row[2]) else row[2],
                "access_token": self._decrypt(row[3]) if (decrypt and row[3]) else row[3],
                "username": row[4],
                "password": self._decrypt(row[5]) if (decrypt and row[5]) else row[5],
                "totp_key": self._decrypt(row[6]) if (decrypt and row[6]) else row[6],
                "token_dir": row[7],
                "is_active": row[8],
                "created_at": row[9].isoformat(),
                "updated_at": row[10].isoformat(),
                "metadata": json.loads(row[11]) if row[11] else None
            }

            return account

    async def list(self, active_only: bool = True) -> List[Dict]:
        """List all trading accounts"""
        async with self._pool.connection() as conn:
            if active_only:
                cursor = await conn.execute("""
                    SELECT account_id, api_key, api_secret, access_token, username,
                           password, totp_key, token_dir, is_active, created_at, updated_at, metadata
                    FROM trading_accounts
                    WHERE is_active = TRUE
                    ORDER BY created_at ASC
                """)
            else:
                cursor = await conn.execute("""
                    SELECT account_id, api_key, api_secret, access_token, username,
                           password, totp_key, token_dir, is_active, created_at, updated_at, metadata
                    FROM trading_accounts
                    ORDER BY created_at ASC
                """)

            rows = await cursor.fetchall()
            accounts = []

            for row in rows:
                account = {
                    "account_id": row[0],
                    "api_key": self._decrypt(row[1]),
                    "api_secret": self._decrypt(row[2]) if row[2] else None,
                    "access_token": self._decrypt(row[3]) if row[3] else None,
                    "username": row[4],
                    "password": self._decrypt(row[5]) if row[5] else None,
                    "totp_key": self._decrypt(row[6]) if row[6] else None,
                    "token_dir": row[7],
                    "is_active": row[8],
                    "created_at": row[9].isoformat(),
                    "updated_at": row[10].isoformat(),
                    "metadata": json.loads(row[11]) if row[11] else None
                }
                accounts.append(account)

            return accounts

    async def update(
        self,
        account_id: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        totp_key: Optional[str] = None,
        token_dir: Optional[str] = None,
        is_active: Optional[bool] = None,
        metadata: Optional[Dict] = None,
        max_retries: int = 3
    ) -> Optional[Dict]:
        """Update a trading account (only updates provided fields)"""
        now = datetime.now(timezone.utc)

        # Build dynamic update query
        updates = []
        params = []

        if api_key is not None:
            updates.append("api_key = %s")
            params.append(self._encrypt(api_key))

        if api_secret is not None:
            updates.append("api_secret = %s")
            params.append(self._encrypt(api_secret) if api_secret else None)

        if access_token is not None:
            updates.append("access_token = %s")
            params.append(self._encrypt(access_token) if access_token else None)

        if username is not None:
            updates.append("username = %s")
            params.append(username)

        if password is not None:
            updates.append("password = %s")
            params.append(self._encrypt(password) if password else None)

        if totp_key is not None:
            updates.append("totp_key = %s")
            params.append(self._encrypt(totp_key) if totp_key else None)

        if token_dir is not None:
            updates.append("token_dir = %s")
            params.append(token_dir)

        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)

        if metadata is not None:
            updates.append("metadata = %s")
            params.append(json.dumps(metadata))

        if not updates:
            # No fields to update
            return await self.get(account_id)

        updates.append("updated_at = %s")
        params.append(now)
        params.append(account_id)

        query = f"""
            UPDATE trading_accounts
            SET {', '.join(updates)}
            WHERE account_id = %s
        """

        for attempt in range(max_retries):
            try:
                async with self._pool.connection() as conn:
                    cursor = await conn.execute(query, params)

                    if cursor.rowcount == 0:
                        return None  # Account not found

                    logger.info(f"Updated trading account: {account_id}")
                    return await self.get(account_id)

            except (psycopg.OperationalError, psycopg.InterfaceError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to update account after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Database error on attempt {attempt + 1}, retrying: {e}")
                await asyncio.sleep(2 ** attempt)

    async def delete(self, account_id: str, soft_delete: bool = True, max_retries: int = 3) -> bool:
        """Delete a trading account (soft delete by default)"""
        if soft_delete:
            # Soft delete: set is_active = False
            result = await self.update(account_id, is_active=False, max_retries=max_retries)
            return result is not None
        else:
            # Hard delete: remove from database
            for attempt in range(max_retries):
                try:
                    async with self._pool.connection() as conn:
                        cursor = await conn.execute("""
                            DELETE FROM trading_accounts
                            WHERE account_id = %s
                        """, (account_id,))

                        deleted = cursor.rowcount > 0
                        if deleted:
                            logger.info(f"Deleted trading account: {account_id}")
                        return deleted

                except (psycopg.OperationalError, psycopg.InterfaceError) as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Failed to delete account after {max_retries} attempts: {e}")
                        raise
                    logger.warning(f"Database error on attempt {attempt + 1}, retrying: {e}")
                    await asyncio.sleep(2 ** attempt)

    async def count(self, active_only: bool = True) -> int:
        """Count trading accounts"""
        async with self._pool.connection() as conn:
            if active_only:
                cursor = await conn.execute("""
                    SELECT COUNT(*) FROM trading_accounts WHERE is_active = TRUE
                """)
            else:
                cursor = await conn.execute("""
                    SELECT COUNT(*) FROM trading_accounts
                """)

            row = await cursor.fetchone()
            return row[0] if row else 0


# Global account store instance
_account_store: Optional[AccountStore] = None


def get_account_store() -> AccountStore:
    """Get the global account store instance"""
    if _account_store is None:
        raise RuntimeError("Account store not initialized. Call initialize_account_store() first.")
    return _account_store


async def initialize_account_store(connection_string: str, encryption_key: Optional[str] = None) -> AccountStore:
    """Initialize the global account store"""
    global _account_store

    if _account_store is not None:
        logger.warning("Account store already initialized")
        return _account_store

    _account_store = AccountStore(connection_string, encryption_key)
    await _account_store.initialize()
    return _account_store
