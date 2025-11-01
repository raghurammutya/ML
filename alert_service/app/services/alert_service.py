"""
Alert Service - Core CRUD Operations
Manages alert lifecycle: create, read, update, delete
"""

import logging
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

import asyncpg

from ..models.alert import Alert, AlertCreate, AlertUpdate
from ..database import DatabaseManager

logger = logging.getLogger(__name__)


class AlertService:
    """
    Core alert management service.
    Handles CRUD operations for alerts.
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def create_alert(
        self,
        user_id: str,
        alert_data: AlertCreate,
        created_by: Optional[str] = None,
    ) -> Alert:
        """
        Create a new alert.

        Args:
            user_id: User identifier (from API key)
            alert_data: Alert creation data
            created_by: Creator identifier (optional)

        Returns:
            Created alert

        Raises:
            ValueError: If validation fails
        """
        try:
            # Extract condition type from condition_config
            condition_type = alert_data.condition_config.get("type", "unknown")

            # Build insert query
            query = """
                INSERT INTO alerts (
                    user_id, account_id, strategy_id, name, description,
                    alert_type, priority, condition_type, condition_config,
                    symbol, symbols, exchange,
                    notification_channels, notification_config, notification_template,
                    evaluation_interval_seconds, evaluation_window_start, evaluation_window_end,
                    max_triggers_per_day, cooldown_seconds,
                    expires_at, created_by, metadata
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                    $16, $17, $18, $19, $20, $21, $22, $23
                )
                RETURNING *
            """

            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    user_id,
                    alert_data.account_id,
                    str(alert_data.strategy_id) if alert_data.strategy_id else None,
                    alert_data.name,
                    alert_data.description,
                    alert_data.alert_type,
                    alert_data.priority,
                    condition_type,
                    json.dumps(alert_data.condition_config),
                    alert_data.symbol,
                    alert_data.symbols,
                    alert_data.exchange,
                    alert_data.notification_channels,
                    json.dumps(alert_data.notification_config) if alert_data.notification_config else None,
                    alert_data.notification_template,
                    alert_data.evaluation_interval_seconds,
                    alert_data.evaluation_window_start,
                    alert_data.evaluation_window_end,
                    alert_data.max_triggers_per_day,
                    alert_data.cooldown_seconds,
                    alert_data.expires_at,
                    created_by or user_id,
                    json.dumps(alert_data.metadata) if alert_data.metadata else None,
                )

            alert = self._row_to_alert(row)
            logger.info(f"Created alert {alert.alert_id} for user {user_id}: {alert.name}")
            return alert

        except asyncpg.UniqueViolationError as e:
            logger.error(f"Unique constraint violation: {e}")
            raise ValueError("Alert with this configuration already exists")
        except Exception as e:
            logger.error(f"Failed to create alert: {e}", exc_info=True)
            raise

    async def get_alert(self, alert_id: UUID, user_id: str) -> Optional[Alert]:
        """
        Get alert by ID (with user ownership check).

        Args:
            alert_id: Alert identifier
            user_id: User identifier for ownership check

        Returns:
            Alert if found and owned by user, None otherwise
        """
        try:
            query = """
                SELECT * FROM alerts
                WHERE alert_id = $1 AND user_id = $2
            """

            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(query, str(alert_id), user_id)

            if row:
                return self._row_to_alert(row)
            return None

        except Exception as e:
            logger.error(f"Failed to get alert {alert_id}: {e}", exc_info=True)
            raise

    async def list_alerts(
        self,
        user_id: str,
        status: Optional[str] = None,
        alert_type: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Alert]:
        """
        List alerts for a user with optional filters.

        Args:
            user_id: User identifier
            status: Filter by status (active, paused, etc.)
            alert_type: Filter by alert type (price, indicator, etc.)
            symbol: Filter by symbol
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of alerts
        """
        try:
            # Build query with filters
            where_clauses = ["user_id = $1"]
            params = [user_id]
            param_counter = 2

            if status:
                where_clauses.append(f"status = ${param_counter}")
                params.append(status)
                param_counter += 1

            if alert_type:
                where_clauses.append(f"alert_type = ${param_counter}")
                params.append(alert_type)
                param_counter += 1

            if symbol:
                where_clauses.append(f"symbol = ${param_counter}")
                params.append(symbol)
                param_counter += 1

            query = f"""
                SELECT * FROM alerts
                WHERE {' AND '.join(where_clauses)}
                ORDER BY created_at DESC
                LIMIT ${param_counter} OFFSET ${param_counter + 1}
            """
            params.extend([limit, offset])

            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            alerts = [self._row_to_alert(row) for row in rows]
            logger.info(f"Retrieved {len(alerts)} alerts for user {user_id}")
            return alerts

        except Exception as e:
            logger.error(f"Failed to list alerts: {e}", exc_info=True)
            raise

    async def update_alert(
        self,
        alert_id: UUID,
        user_id: str,
        update_data: AlertUpdate,
    ) -> Optional[Alert]:
        """
        Update an existing alert.

        Args:
            alert_id: Alert identifier
            user_id: User identifier for ownership check
            update_data: Fields to update

        Returns:
            Updated alert if found, None otherwise
        """
        try:
            # Build dynamic UPDATE query
            update_fields = []
            params = []
            param_counter = 1

            # Map update_data fields to database columns
            field_mapping = {
                "name": "name",
                "description": "description",
                "priority": "priority",
                "condition_config": "condition_config",
                "status": "status",
                "notification_channels": "notification_channels",
                "notification_config": "notification_config",
                "notification_template": "notification_template",
                "evaluation_interval_seconds": "evaluation_interval_seconds",
                "evaluation_window_start": "evaluation_window_start",
                "evaluation_window_end": "evaluation_window_end",
                "max_triggers_per_day": "max_triggers_per_day",
                "cooldown_seconds": "cooldown_seconds",
                "expires_at": "expires_at",
                "metadata": "metadata",
            }

            for field, db_column in field_mapping.items():
                value = getattr(update_data, field, None)
                if value is not None:
                    update_fields.append(f"{db_column} = ${param_counter}")

                    # Handle JSONB fields
                    if field in ["condition_config", "notification_config", "metadata"]:
                        params.append(json.dumps(value))
                    else:
                        params.append(value)
                    param_counter += 1

            if not update_fields:
                logger.warning(f"No fields to update for alert {alert_id}")
                return await self.get_alert(alert_id, user_id)

            # Add updated_at
            update_fields.append("updated_at = NOW()")

            query = f"""
                UPDATE alerts
                SET {', '.join(update_fields)}
                WHERE alert_id = ${param_counter} AND user_id = ${param_counter + 1}
                RETURNING *
            """
            params.extend([str(alert_id), user_id])

            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(query, *params)

            if row:
                alert = self._row_to_alert(row)
                logger.info(f"Updated alert {alert_id} for user {user_id}")
                return alert

            logger.warning(f"Alert {alert_id} not found or not owned by user {user_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to update alert {alert_id}: {e}", exc_info=True)
            raise

    async def delete_alert(self, alert_id: UUID, user_id: str) -> bool:
        """
        Delete an alert (soft delete by setting status='deleted').

        Args:
            alert_id: Alert identifier
            user_id: User identifier for ownership check

        Returns:
            True if deleted, False if not found
        """
        try:
            query = """
                UPDATE alerts
                SET status = 'deleted', updated_at = NOW()
                WHERE alert_id = $1 AND user_id = $2
                RETURNING alert_id
            """

            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(query, str(alert_id), user_id)

            if row:
                logger.info(f"Deleted alert {alert_id} for user {user_id}")
                return True

            logger.warning(f"Alert {alert_id} not found or not owned by user {user_id}")
            return False

        except Exception as e:
            logger.error(f"Failed to delete alert {alert_id}: {e}", exc_info=True)
            raise

    async def pause_alert(self, alert_id: UUID, user_id: str) -> bool:
        """
        Pause an alert (stop evaluation).

        Args:
            alert_id: Alert identifier
            user_id: User identifier for ownership check

        Returns:
            True if paused, False if not found
        """
        try:
            query = """
                UPDATE alerts
                SET status = 'paused', updated_at = NOW()
                WHERE alert_id = $1 AND user_id = $2 AND status = 'active'
                RETURNING alert_id
            """

            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(query, str(alert_id), user_id)

            if row:
                logger.info(f"Paused alert {alert_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to pause alert {alert_id}: {e}", exc_info=True)
            raise

    async def resume_alert(self, alert_id: UUID, user_id: str) -> bool:
        """
        Resume a paused alert.

        Args:
            alert_id: Alert identifier
            user_id: User identifier for ownership check

        Returns:
            True if resumed, False if not found
        """
        try:
            query = """
                UPDATE alerts
                SET status = 'active', updated_at = NOW()
                WHERE alert_id = $1 AND user_id = $2 AND status = 'paused'
                RETURNING alert_id
            """

            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(query, str(alert_id), user_id)

            if row:
                logger.info(f"Resumed alert {alert_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to resume alert {alert_id}: {e}", exc_info=True)
            raise

    async def get_alert_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get alert statistics for a user.

        Args:
            user_id: User identifier

        Returns:
            Dictionary with alert statistics
        """
        try:
            query = """
                SELECT
                    COUNT(*) as total_alerts,
                    COUNT(*) FILTER (WHERE status = 'active') as active_alerts,
                    COUNT(*) FILTER (WHERE status = 'paused') as paused_alerts,
                    COUNT(*) FILTER (WHERE status = 'triggered') as triggered_alerts,
                    SUM(trigger_count) as total_triggers,
                    MAX(last_triggered_at) as last_trigger_time
                FROM alerts
                WHERE user_id = $1 AND status != 'deleted'
            """

            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(query, user_id)

            stats = {
                "total_alerts": row["total_alerts"] or 0,
                "active_alerts": row["active_alerts"] or 0,
                "paused_alerts": row["paused_alerts"] or 0,
                "triggered_alerts": row["triggered_alerts"] or 0,
                "total_triggers": row["total_triggers"] or 0,
                "last_trigger_time": row["last_trigger_time"].isoformat() if row["last_trigger_time"] else None,
            }

            return stats

        except Exception as e:
            logger.error(f"Failed to get alert stats: {e}", exc_info=True)
            raise

    def _row_to_alert(self, row: asyncpg.Record) -> Alert:
        """
        Convert database row to Alert model.

        Args:
            row: Database row

        Returns:
            Alert instance
        """
        return Alert(
            alert_id=row["alert_id"],
            user_id=row["user_id"],
            account_id=row["account_id"],
            strategy_id=row["strategy_id"],
            name=row["name"],
            description=row["description"],
            alert_type=row["alert_type"],
            priority=row["priority"],
            condition_type=row["condition_type"],
            condition_config=row["condition_config"],
            symbol=row["symbol"],
            symbols=row["symbols"],
            exchange=row["exchange"],
            notification_channels=row["notification_channels"],
            notification_config=row["notification_config"],
            notification_template=row["notification_template"],
            status=row["status"],
            evaluation_interval_seconds=row["evaluation_interval_seconds"],
            evaluation_window_start=row["evaluation_window_start"],
            evaluation_window_end=row["evaluation_window_end"],
            max_triggers_per_day=row["max_triggers_per_day"],
            cooldown_seconds=row["cooldown_seconds"],
            trigger_count=row["trigger_count"],
            last_triggered_at=row["last_triggered_at"],
            last_evaluated_at=row["last_evaluated_at"],
            evaluation_count=row["evaluation_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
            created_by=row["created_by"],
            metadata=row["metadata"],
        )
