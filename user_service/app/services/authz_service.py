"""
Authorization Service - Policy evaluation engine (PDP)

This service implements Attribute-Based Access Control (ABAC) with:
- Pattern matching for subjects, actions, and resources
- Policy priority and effect resolution (DENY overrides ALLOW)
- Context-based evaluation with conditions
- Redis caching for performance
- Trading account ownership and membership checks
"""

import re
import time
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.core.config import settings
from app.core.redis_client import RedisClient
from app.models import Policy, PolicyEffect, TradingAccount, TradingAccountMembership


class AuthzService:
    """Service for authorization and policy evaluation"""

    def __init__(self, db: Session, redis: RedisClient):
        self.db = db
        self.redis = redis

    def check_permission(
        self,
        subject: str,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Check if subject is authorized to perform action on resource

        This is the main Policy Decision Point (PDP) entry point.

        Args:
            subject: Subject identifier (e.g., "user:123", "service:ticker_service")
            action: Action to perform (e.g., "trade:place_order", "account:view")
            resource: Resource identifier (e.g., "trading_account:456")
            context: Additional context for policy evaluation
            use_cache: Whether to use Redis cache

        Returns:
            Tuple of (allowed: bool, decision: str, matched_policy: Optional[str])
            - allowed: Whether the action is permitted
            - decision: "allow", "deny", or "default_deny"
            - matched_policy: Name of the policy that matched (if any)
        """
        start_time = time.time()

        # Check cache first
        if use_cache:
            cached_decision = self._get_cached_decision(subject, action, resource)
            if cached_decision is not None:
                return cached_decision

        # Extract IDs for special handling
        subject_type, subject_id = self._parse_identifier(subject)
        resource_type, resource_id = self._parse_identifier(resource)

        # Special case: Trading account ownership and membership
        if resource_type == "trading_account" and subject_type == "user":
            ownership_check = self._check_trading_account_access(
                int(subject_id), int(resource_id), action
            )
            if ownership_check is not None:
                decision = ownership_check
                self._cache_decision(subject, action, resource, decision)
                return decision

        # Fetch applicable policies
        policies = self._fetch_applicable_policies(subject, action, resource)

        if not policies:
            # Default deny if no policies match
            decision = (False, "default_deny", None)
            self._cache_decision(subject, action, resource, decision)
            return decision

        # Evaluate policies
        decision = self._evaluate_policies(policies, subject, action, resource, context)

        # Cache the decision
        if use_cache:
            self._cache_decision(subject, action, resource, decision)

        return decision

    def _check_trading_account_access(
        self,
        user_id: int,
        trading_account_id: int,
        action: str
    ) -> Optional[Tuple[bool, str, Optional[str]]]:
        """
        Check if user has access to trading account through ownership or membership

        Args:
            user_id: User ID
            trading_account_id: Trading account ID
            action: Action being performed

        Returns:
            Tuple of (allowed, decision, reason) or None if not applicable
        """
        # Check ownership
        account = self.db.query(TradingAccount).filter(
            TradingAccount.trading_account_id == trading_account_id,
            TradingAccount.user_id == user_id
        ).first()

        if account:
            # Owner has full access
            return (True, "allow", "Trading Account Owner")

        # Check membership
        membership = self.db.query(TradingAccountMembership).filter(
            TradingAccountMembership.trading_account_id == trading_account_id,
            TradingAccountMembership.user_id == user_id
        ).first()

        if membership:
            # Check permissions based on action
            required_permission = self._map_action_to_permission(action)

            if required_permission == "view" and membership.can_view:
                return (True, "allow", "Trading Account Membership")
            elif required_permission == "trade" and membership.can_trade:
                return (True, "allow", "Trading Account Membership")
            elif required_permission == "manage" and membership.can_manage:
                return (True, "allow", "Trading Account Membership")
            else:
                return (False, "deny", "Insufficient Membership Permissions")

        # No ownership or membership found
        return None

    def _map_action_to_permission(self, action: str) -> str:
        """
        Map action string to permission level

        Args:
            action: Action string (e.g., "trade:place_order")

        Returns:
            Permission level: "view", "trade", or "manage"
        """
        if "view" in action.lower() or "read" in action.lower():
            return "view"
        elif "trade" in action.lower() or "order" in action.lower():
            return "trade"
        elif "manage" in action.lower() or "admin" in action.lower() or "delete" in action.lower():
            return "manage"
        else:
            return "view"  # Default to most restrictive

    def _fetch_applicable_policies(
        self,
        subject: str,
        action: str,
        resource: str
    ) -> List[Policy]:
        """
        Fetch policies that could apply to this authorization request

        Uses pattern matching to find relevant policies.

        Args:
            subject: Subject identifier
            action: Action
            resource: Resource identifier

        Returns:
            List of applicable policies ordered by priority (highest first)
        """
        # Fetch all enabled policies, ordered by priority (highest first)
        policies = self.db.query(Policy).filter(
            Policy.enabled == True
        ).order_by(Policy.priority.desc()).all()

        # Filter policies that match subject, action, and resource patterns
        applicable_policies = []
        for policy in policies:
            if (self._matches_pattern(subject, policy.subjects) and
                self._matches_pattern(action, policy.actions) and
                self._matches_pattern(resource, policy.resources)):
                applicable_policies.append(policy)

        return applicable_policies

    def _matches_pattern(self, value: str, patterns: List[str]) -> bool:
        """
        Check if value matches any of the patterns

        Supports wildcards:
        - "*" matches any single segment
        - "**" matches zero or more segments

        Examples:
        - "user:*" matches "user:123", "user:456"
        - "trade:*" matches "trade:place_order", "trade:cancel_order"
        - "*:*" matches any pattern with exactly two segments

        Args:
            value: Value to check (e.g., "user:123")
            patterns: List of patterns to match against

        Returns:
            True if value matches any pattern
        """
        for pattern in patterns:
            # Convert glob pattern to regex
            # Escape special regex characters except * and :
            regex_pattern = pattern.replace('.', r'\.')
            regex_pattern = regex_pattern.replace('*', '.*')
            regex_pattern = f"^{regex_pattern}$"

            if re.match(regex_pattern, value):
                return True

        return False

    def _evaluate_policies(
        self,
        policies: List[Policy],
        subject: str,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Evaluate policies to make authorization decision

        Policy evaluation rules:
        1. Policies are evaluated in priority order (highest first)
        2. DENY effect always overrides ALLOW
        3. First matching DENY immediately returns deny
        4. If no DENY matches and at least one ALLOW matches, return allow
        5. If no policies match, return default deny

        Args:
            policies: List of applicable policies (already ordered by priority)
            subject: Subject identifier
            action: Action
            resource: Resource identifier
            context: Additional context

        Returns:
            Tuple of (allowed, decision, matched_policy_name)
        """
        allow_policy = None

        for policy in policies:
            # Check conditions if present
            if policy.conditions and not self._evaluate_conditions(policy.conditions, context):
                continue

            # Policy matches - check effect
            if policy.effect == PolicyEffect.DENY:
                # DENY always wins - return immediately
                return (False, "deny", policy.name)
            elif policy.effect == PolicyEffect.ALLOW:
                # Store first ALLOW but continue checking for DENY
                if allow_policy is None:
                    allow_policy = policy

        # If we found an ALLOW policy and no DENY, allow the action
        if allow_policy:
            return (True, "allow", allow_policy.name)

        # No matching policies or only non-matching policies
        return (False, "default_deny", None)

    def _evaluate_conditions(
        self,
        conditions: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Evaluate policy conditions against context

        Supports basic condition operators:
        - equals: value must equal specified value
        - in: value must be in list
        - not_in: value must not be in list
        - greater_than: value must be greater than specified value
        - less_than: value must be less than specified value

        Args:
            conditions: Policy conditions from database
            context: Request context

        Returns:
            True if all conditions are satisfied
        """
        if not context:
            # No context provided, conditions cannot be evaluated
            return False

        for key, condition_spec in conditions.items():
            if key not in context:
                # Required context key is missing
                return False

            context_value = context[key]

            # Handle different condition operators
            if isinstance(condition_spec, dict):
                operator = condition_spec.get('operator')
                expected_value = condition_spec.get('value')

                if operator == 'equals' and context_value != expected_value:
                    return False
                elif operator == 'in' and context_value not in expected_value:
                    return False
                elif operator == 'not_in' and context_value in expected_value:
                    return False
                elif operator == 'greater_than' and context_value <= expected_value:
                    return False
                elif operator == 'less_than' and context_value >= expected_value:
                    return False
            else:
                # Simple equality check
                if context_value != condition_spec:
                    return False

        return True

    def _get_cached_decision(
        self,
        subject: str,
        action: str,
        resource: str
    ) -> Optional[Tuple[bool, str, Optional[str]]]:
        """
        Get cached authorization decision from Redis

        Args:
            subject: Subject identifier
            action: Action
            resource: Resource identifier

        Returns:
            Cached decision tuple or None if not cached
        """
        decision = self.redis.get_authz_decision(subject, resource, action)
        if decision:
            # Cached decision format: "allow:PolicyName" or "deny:PolicyName"
            parts = decision.split(":", 1)
            allowed = parts[0] == "allow"
            matched_policy = parts[1] if len(parts) > 1 else None
            return (allowed, parts[0], matched_policy)
        return None

    def _cache_decision(
        self,
        subject: str,
        action: str,
        resource: str,
        decision: Tuple[bool, str, Optional[str]]
    ) -> None:
        """
        Cache authorization decision in Redis

        Args:
            subject: Subject identifier
            action: Action
            resource: Resource identifier
            decision: Decision tuple (allowed, decision_type, matched_policy)
        """
        allowed, decision_type, matched_policy = decision
        cache_value = f"{decision_type}:{matched_policy or ''}"
        self.redis.set_authz_decision(subject, resource, action, cache_value)

    def invalidate_cache(
        self,
        subject: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None
    ) -> int:
        """
        Invalidate authorization cache

        Args:
            subject: Invalidate for specific subject (or None for all)
            action: Invalidate for specific action (or None for all)
            resource: Invalidate for specific resource (or None for all)

        Returns:
            Number of cache keys invalidated
        """
        if subject or action or resource:
            # Targeted invalidation
            return self.redis.invalidate_authz_cache(subject, resource, action)
        else:
            # Invalidate entire authz cache
            pattern = f"{settings.REDIS_KEY_PREFIX}:authz:*"
            keys = self.redis.client.keys(pattern)
            if keys:
                self.redis.client.delete(*keys)
            return len(keys)

    def _parse_identifier(self, identifier: str) -> Tuple[str, str]:
        """
        Parse identifier into type and ID

        Examples:
        - "user:123" -> ("user", "123")
        - "service:ticker_service" -> ("service", "ticker_service")
        - "trading_account:456" -> ("trading_account", "456")

        Args:
            identifier: Identifier string

        Returns:
            Tuple of (type, id)
        """
        parts = identifier.split(":", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        else:
            return identifier, ""

    def list_policies(
        self,
        enabled_only: bool = True,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Policy], int]:
        """
        List authorization policies

        Args:
            enabled_only: Only return enabled policies
            page: Page number (1-indexed)
            page_size: Number of policies per page

        Returns:
            Tuple of (policies, total_count)
        """
        query = self.db.query(Policy)

        if enabled_only:
            query = query.filter(Policy.enabled == True)

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        policies = query.order_by(Policy.priority.desc()).offset(offset).limit(page_size).all()

        return policies, total

    def check_trading_account_permission(
        self,
        user_id: int,
        trading_account_id: int,
        permission: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Simplified check for trading account permissions

        Args:
            user_id: User ID
            trading_account_id: Trading account ID
            permission: Permission level ("view", "trade", "manage")

        Returns:
            Tuple of (has_permission, source, membership_role)
            - has_permission: Whether user has the permission
            - source: "owner", "membership", or None
            - membership_role: Role if source is membership
        """
        # Check ownership
        account = self.db.query(TradingAccount).filter(
            TradingAccount.trading_account_id == trading_account_id,
            TradingAccount.user_id == user_id
        ).first()

        if account:
            return (True, "owner", None)

        # Check membership
        membership = self.db.query(TradingAccountMembership).filter(
            TradingAccountMembership.trading_account_id == trading_account_id,
            TradingAccountMembership.user_id == user_id
        ).first()

        if membership:
            has_permission = False
            if permission == "view" and membership.can_view:
                has_permission = True
            elif permission == "trade" and membership.can_trade:
                has_permission = True
            elif permission == "manage" and membership.can_manage:
                has_permission = True

            # Infer role from permissions
            role = None
            if membership.can_manage:
                role = "admin"
            elif membership.can_trade:
                role = "trader"
            elif membership.can_view:
                role = "viewer"

            return (has_permission, "membership" if has_permission else None, role)

        return (False, None, None)
