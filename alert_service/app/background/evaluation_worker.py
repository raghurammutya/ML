"""
Alert Evaluation Worker
Background task that continuously evaluates active alerts and triggers notifications
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from ..config import get_settings
from ..database import DatabaseManager
from ..services.evaluator import ConditionEvaluator, EvaluationResult
from ..services.notification_service import NotificationService

logger = logging.getLogger(__name__)
settings = get_settings()


class EvaluationWorker:
    """
    Background worker that evaluates active alerts.

    Features:
    - Continuous evaluation loop
    - Priority-based batching (critical → high → medium → low)
    - Cooldown period enforcement
    - Daily trigger limit enforcement
    - Notification dispatch on match
    - Alert event recording
    - Error handling with exponential backoff
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        notification_service: NotificationService,
        evaluator: Optional[ConditionEvaluator] = None,
    ):
        self.db = db_manager
        self.notification_service = notification_service
        self.evaluator = evaluator or ConditionEvaluator()

        self.running = False
        self.task: Optional[asyncio.Task] = None

        # Configuration
        self.batch_size = settings.evaluation_batch_size
        self.concurrency = settings.evaluation_concurrency
        self.min_interval = settings.min_evaluation_interval

        # Priority order (highest to lowest)
        self.priority_order = ["critical", "high", "medium", "low"]

    async def start(self):
        """Start the evaluation worker."""
        if self.running:
            logger.warning("Evaluation worker is already running")
            return

        self.running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info("Evaluation worker started")

    async def stop(self):
        """Stop the evaluation worker."""
        if not self.running:
            logger.warning("Evaluation worker is not running")
            return

        logger.info("Stopping evaluation worker...")
        self.running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        # Close evaluator's HTTP client
        await self.evaluator.close()

        logger.info("Evaluation worker stopped")

    async def _run_loop(self):
        """Main evaluation loop."""
        logger.info("Evaluation loop started")

        while self.running:
            try:
                cycle_start = datetime.utcnow()

                # Fetch and evaluate alerts for each priority
                total_evaluated = 0
                for priority in self.priority_order:
                    if not self.running:
                        break

                    evaluated_count = await self._evaluate_priority_batch(priority)
                    total_evaluated += evaluated_count

                cycle_duration = (datetime.utcnow() - cycle_start).total_seconds()

                if total_evaluated > 0:
                    logger.info(
                        f"Evaluation cycle complete: {total_evaluated} alerts evaluated in {cycle_duration:.2f}s"
                    )

                # Sleep before next cycle
                sleep_time = max(self.min_interval - cycle_duration, 1)
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                logger.info("Evaluation loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in evaluation loop: {e}", exc_info=True)
                # Exponential backoff on error
                await asyncio.sleep(min(60, self.min_interval * 2))

        logger.info("Evaluation loop stopped")

    async def _evaluate_priority_batch(self, priority: str) -> int:
        """
        Evaluate a batch of alerts for a specific priority.

        Args:
            priority: Priority level (critical, high, medium, low)

        Returns:
            Number of alerts evaluated
        """
        try:
            # Fetch alerts due for evaluation
            alerts = await self._fetch_alerts_for_evaluation(priority, self.batch_size)

            if not alerts:
                return 0

            logger.debug(f"Evaluating {len(alerts)} {priority} priority alerts")

            # Evaluate alerts concurrently with limited concurrency
            tasks = []
            for alert in alerts:
                task = asyncio.create_task(self._evaluate_alert(alert))
                tasks.append(task)

                # Limit concurrency
                if len(tasks) >= self.concurrency:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    tasks = []

            # Evaluate remaining tasks
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            return len(alerts)

        except Exception as e:
            logger.error(f"Error evaluating {priority} priority batch: {e}", exc_info=True)
            return 0

    async def _fetch_alerts_for_evaluation(self, priority: str, limit: int) -> List[dict]:
        """
        Fetch active alerts that are due for evaluation.

        Criteria:
        - status = 'active'
        - priority = specified priority
        - evaluation_interval elapsed since last_evaluated_at
        - OR never evaluated (last_evaluated_at IS NULL)
        """
        query = """
            SELECT
                alert_id,
                user_id,
                name,
                alert_type,
                priority,
                condition_config,
                notification_channels,
                evaluation_interval_seconds,
                cooldown_seconds,
                max_triggers_per_day,
                trigger_count,
                last_triggered_at,
                last_evaluated_at
            FROM alerts
            WHERE status = 'active'
              AND priority = $1
              AND (
                  last_evaluated_at IS NULL
                  OR last_evaluated_at + (evaluation_interval_seconds || ' seconds')::interval < NOW()
              )
            ORDER BY
                COALESCE(last_evaluated_at, '1970-01-01'::timestamptz) ASC,
                created_at ASC
            LIMIT $2
        """

        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch(query, priority, limit)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching alerts for evaluation: {e}", exc_info=True)
            return []

    async def _evaluate_alert(self, alert: dict) -> None:
        """
        Evaluate a single alert.

        Steps:
        1. Evaluate condition using ConditionEvaluator
        2. Update last_evaluated_at
        3. If condition matches:
           - Check cooldown period
           - Check daily trigger limit
           - Trigger notification
           - Record alert event
           - Update trigger count and last_triggered_at
        """
        alert_id = alert["alert_id"]
        user_id = alert["user_id"]

        try:
            # Evaluate condition
            result: EvaluationResult = await self.evaluator.evaluate(alert["condition_config"])

            # Update last_evaluated_at
            await self._update_last_evaluated(alert_id)

            # If condition doesn't match, we're done
            if not result.matched:
                logger.debug(f"Alert {alert_id} condition not met")
                return

            logger.info(f"Alert {alert_id} condition matched!")

            # Check if alert can be triggered
            can_trigger, skip_reason = await self._check_can_trigger(alert)

            if not can_trigger:
                logger.info(f"Alert {alert_id} trigger skipped: {skip_reason}")
                return

            # Trigger notification
            await self._trigger_alert(alert, result)

        except Exception as e:
            logger.error(f"Error evaluating alert {alert_id}: {e}", exc_info=True)

    async def _update_last_evaluated(self, alert_id: UUID) -> None:
        """Update alert's last_evaluated_at timestamp."""
        query = """
            UPDATE alerts
            SET last_evaluated_at = NOW()
            WHERE alert_id = $1
        """

        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute(query, alert_id)
        except Exception as e:
            logger.error(f"Error updating last_evaluated_at for {alert_id}: {e}")

    async def _check_can_trigger(self, alert: dict) -> tuple[bool, Optional[str]]:
        """
        Check if alert can be triggered.

        Checks:
        1. Cooldown period not violated
        2. Daily trigger limit not exceeded

        Returns:
            (can_trigger, skip_reason)
        """
        alert_id = alert["alert_id"]

        # Check cooldown period
        cooldown_seconds = alert.get("cooldown_seconds", 0)
        last_triggered_at = alert.get("last_triggered_at")

        if cooldown_seconds > 0 and last_triggered_at:
            cooldown_until = last_triggered_at + timedelta(seconds=cooldown_seconds)
            if datetime.utcnow() < cooldown_until:
                remaining = (cooldown_until - datetime.utcnow()).total_seconds()
                return False, f"cooldown active ({remaining:.0f}s remaining)"

        # Check daily trigger limit
        max_triggers_per_day = alert.get("max_triggers_per_day")

        if max_triggers_per_day and max_triggers_per_day > 0:
            # Count triggers in last 24 hours
            trigger_count_today = await self._get_trigger_count_today(alert_id)

            if trigger_count_today >= max_triggers_per_day:
                return False, f"daily limit reached ({trigger_count_today}/{max_triggers_per_day})"

        return True, None

    async def _get_trigger_count_today(self, alert_id: UUID) -> int:
        """Get number of times alert was triggered in last 24 hours."""
        query = """
            SELECT COUNT(*)
            FROM alert_events
            WHERE alert_id = $1
              AND triggered_at >= NOW() - INTERVAL '24 hours'
        """

        try:
            async with self.db.pool.acquire() as conn:
                count = await conn.fetchval(query, alert_id)
                return count or 0
        except Exception as e:
            logger.error(f"Error getting trigger count for {alert_id}: {e}")
            return 0

    async def _trigger_alert(self, alert: dict, result: EvaluationResult) -> None:
        """
        Trigger alert: send notification and record event.

        Args:
            alert: Alert data
            result: Evaluation result
        """
        alert_id = alert["alert_id"]
        user_id = alert["user_id"]

        try:
            # Format notification message
            message = self._format_notification_message(alert, result)

            # Send notification to all configured channels
            channels = alert.get("notification_channels", ["telegram"])

            notification_results = await self.notification_service.send_notification(
                user_id=user_id,
                alert_id=alert_id,
                message=message,
                priority=alert["priority"],
                channels=channels,
                metadata={
                    "alert_name": alert["name"],
                    "alert_type": alert["alert_type"],
                    "current_value": result.current_value,
                    "threshold": result.threshold,
                    "alert_id": str(alert_id),
                }
            )

            # Record alert event
            await self._record_alert_event(
                alert_id=alert_id,
                evaluation_result=result.to_dict(),
                notification_results=notification_results,
            )

            # Update alert statistics
            await self._update_alert_triggered(alert_id)

            logger.info(
                f"Alert {alert_id} triggered successfully. "
                f"Notifications sent: {sum(1 for r in notification_results.values() if r.get('success'))}/{len(notification_results)}"
            )

        except Exception as e:
            logger.error(f"Error triggering alert {alert_id}: {e}", exc_info=True)

    def _format_notification_message(self, alert: dict, result: EvaluationResult) -> str:
        """
        Format notification message for alert trigger.

        Args:
            alert: Alert data
            result: Evaluation result

        Returns:
            Formatted message string
        """
        alert_type = alert["alert_type"]
        name = alert["name"]

        message_parts = [f"🔔 **{name}**"]

        if alert_type == "price":
            symbol = alert["condition_config"].get("symbol", "")
            message_parts.append(f"Symbol: {symbol}")
            if result.current_value:
                message_parts.append(f"Current Price: {result.current_value:.2f}")
            if result.threshold:
                message_parts.append(f"Threshold: {result.threshold:.2f}")

        elif alert_type == "position":
            metric = alert["condition_config"].get("metric", "pnl")
            message_parts.append(f"Metric: {metric.upper()}")
            if result.current_value:
                message_parts.append(f"Current Value: {result.current_value:.2f}")
            if result.threshold:
                message_parts.append(f"Threshold: {result.threshold:.2f}")

        elif alert_type == "indicator":
            symbol = alert["condition_config"].get("symbol", "")
            indicator = alert["condition_config"].get("indicator", "")
            message_parts.append(f"Symbol: {symbol}")
            message_parts.append(f"Indicator: {indicator.upper()}")
            if result.current_value:
                message_parts.append(f"Current Value: {result.current_value:.2f}")
            if result.threshold:
                message_parts.append(f"Threshold: {result.threshold:.2f}")

        else:
            # Generic format for other types
            if result.current_value:
                message_parts.append(f"Current Value: {result.current_value}")
            if result.threshold:
                message_parts.append(f"Threshold: {result.threshold}")

        # Add timestamp
        message_parts.append(f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        return "\n".join(message_parts)

    async def _record_alert_event(
        self,
        alert_id: UUID,
        evaluation_result: dict,
        notification_results: dict,
    ) -> None:
        """
        Record alert event in database.

        Args:
            alert_id: Alert ID
            evaluation_result: Result of condition evaluation
            notification_results: Results of notification dispatch
        """
        query = """
            INSERT INTO alert_events (
                alert_id,
                triggered_at,
                evaluation_result,
                notification_results
            ) VALUES ($1, NOW(), $2, $3)
        """

        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute(
                    query,
                    alert_id,
                    evaluation_result,
                    notification_results,
                )
        except Exception as e:
            logger.error(f"Error recording alert event for {alert_id}: {e}")

    async def _update_alert_triggered(self, alert_id: UUID) -> None:
        """
        Update alert after triggering.

        Updates:
        - trigger_count: increment by 1
        - last_triggered_at: set to NOW()
        """
        query = """
            UPDATE alerts
            SET
                trigger_count = trigger_count + 1,
                last_triggered_at = NOW()
            WHERE alert_id = $1
        """

        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute(query, alert_id)
        except Exception as e:
            logger.error(f"Error updating alert triggered stats for {alert_id}: {e}")

    async def evaluate_once(self, alert_id: UUID) -> Optional[EvaluationResult]:
        """
        Evaluate a single alert once (for testing/manual trigger).

        Args:
            alert_id: Alert ID to evaluate

        Returns:
            EvaluationResult or None if alert not found
        """
        query = """
            SELECT condition_config
            FROM alerts
            WHERE alert_id = $1
        """

        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(query, alert_id)

            if not row:
                return None

            result = await self.evaluator.evaluate(row["condition_config"])
            return result

        except Exception as e:
            logger.error(f"Error evaluating alert {alert_id}: {e}", exc_info=True)
            return None
