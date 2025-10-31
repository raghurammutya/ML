"""
Database Persistence for OrderTasks

Tasks survive service restarts by storing in PostgreSQL.
"""
from __future__ import annotations

import asyncio
import json
from typing import List, Optional
from datetime import datetime

from loguru import logger
import psycopg
from psycopg_pool import AsyncConnectionPool

from .order_executor import OrderTask, TaskStatus


class TaskStore:
    """PostgreSQL storage for OrderTasks"""

    def __init__(self, connection_string: str):
        self._pool: Optional[AsyncConnectionPool] = None
        self._connection_string = connection_string

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
                CREATE TABLE IF NOT EXISTS order_tasks (
                    task_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    params JSONB NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 5,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    last_error TEXT,
                    result JSONB,
                    account_id TEXT NOT NULL,
                    UNIQUE(idempotency_key)
                )
            """)

            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_order_tasks_status
                ON order_tasks(status) WHERE status IN ('pending', 'retrying')
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_order_tasks_account
                ON order_tasks(account_id)
            """)

        logger.info("Task store initialized")

    async def save(self, task: OrderTask, max_retries: int = 3) -> None:
        """Save or update a task with retry logic"""
        for attempt in range(max_retries):
            try:
                async with self._pool.connection() as conn:
                    await conn.execute("""
                        INSERT INTO order_tasks
                        (task_id, idempotency_key, operation, params, status, attempts,
                         max_attempts, created_at, updated_at, last_error, result, account_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (task_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            attempts = EXCLUDED.attempts,
                            updated_at = EXCLUDED.updated_at,
                            last_error = EXCLUDED.last_error,
                            result = EXCLUDED.result
                    """, (
                        task.task_id,
                        task.idempotency_key,
                        task.operation,
                        json.dumps(task.params),
                        task.status.value,
                        task.attempts,
                        task.max_attempts,
                        task.created_at,
                        task.updated_at,
                        task.last_error,
                        json.dumps(task.result) if task.result else None,
                        task.account_id
                    ))
                return  # Success
            except (psycopg.OperationalError, psycopg.InterfaceError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to save task {task.task_id} after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Database error on attempt {attempt + 1}/{max_retries}, retrying: {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s

    async def load_pending(self) -> List[OrderTask]:
        """Load all pending/retrying tasks (for service restart recovery)"""
        async with self._pool.connection() as conn:
            cursor = await conn.execute("""
                SELECT task_id, idempotency_key, operation, params, status, attempts,
                       max_attempts, created_at, updated_at, last_error, result, account_id
                FROM order_tasks
                WHERE status IN ('pending', 'retrying')
                ORDER BY created_at
            """)
            rows = await cursor.fetchall()

        tasks = []
        for row in rows:
            task = OrderTask(
                task_id=row[0],
                idempotency_key=row[1],
                operation=row[2],
                params=json.loads(row[3]),
                status=TaskStatus(row[4]),
                attempts=row[5],
                max_attempts=row[6],
                created_at=row[7],
                updated_at=row[8],
                last_error=row[9],
                result=json.loads(row[10]) if row[10] else None,
                account_id=row[11]
            )
            tasks.append(task)

        logger.info(f"Loaded {len(tasks)} pending tasks from database")
        return tasks

    async def get(self, task_id: str) -> Optional[OrderTask]:
        """Get a single task by ID"""
        async with self._pool.connection() as conn:
            cursor = await conn.execute("""
                SELECT task_id, idempotency_key, operation, params, status, attempts,
                       max_attempts, created_at, updated_at, last_error, result, account_id
                FROM order_tasks
                WHERE task_id = %s
            """, (task_id,))
            row = await cursor.fetchone()

        if not row:
            return None

        return OrderTask(
            task_id=row[0],
            idempotency_key=row[1],
            operation=row[2],
            params=json.loads(row[3]),
            status=TaskStatus(row[4]),
            attempts=row[5],
            max_attempts=row[6],
            created_at=row[7],
            updated_at=row[8],
            last_error=row[9],
            result=json.loads(row[10]) if row[10] else None,
            account_id=row[11]
        )

    async def delete_old_completed(self, days: int = 7) -> int:
        """Delete completed tasks older than N days"""
        if not isinstance(days, int) or days < 1:
            raise ValueError("days must be a positive integer")

        async with self._pool.connection() as conn:
            cursor = await conn.execute("""
                DELETE FROM order_tasks
                WHERE status IN ('completed', 'failed', 'dead_letter')
                AND updated_at < NOW() - make_interval(days => %s)
            """, (days,))
            return cursor.rowcount

    async def close(self) -> None:
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
