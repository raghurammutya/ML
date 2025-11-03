"""
User Service - Profile management and user operations
"""

from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.core.config import settings
from app.core.redis_client import RedisClient
from app.models import User, UserStatus, UserPreference, UserRole, Role, TradingAccount, AuthEvent
from app.utils.security import mask_email, mask_ip
from app.services.event_service import EventService


class UserService:
    """Service for user profile and preference management"""

    def __init__(self, db: Session, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.event_service = EventService(redis)

    def get_user_profile(self, user_id: int) -> Optional[User]:
        """
        Get user profile by ID

        Args:
            user_id: User ID

        Returns:
            User object with relationships loaded or None if not found
        """
        user = self.db.query(User).filter(User.user_id == user_id).first()
        return user

    def update_user_profile(
        self,
        user_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None
    ) -> Tuple[User, List[str]]:
        """
        Update user profile

        Args:
            user_id: User ID
            name: New name (optional)
            phone: New phone (optional)
            timezone: New timezone (optional)
            locale: New locale (optional)

        Returns:
            Tuple of (updated_user, list_of_updated_fields)

        Raises:
            ValueError: If user not found
        """
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        updated_fields = []

        if name is not None and name != user.name:
            user.name = name
            updated_fields.append("name")

        if phone is not None and phone != user.phone:
            user.phone = phone
            updated_fields.append("phone")

        if timezone is not None and timezone != user.timezone:
            user.timezone = timezone
            updated_fields.append("timezone")

        if locale is not None and locale != user.locale:
            user.locale = locale
            updated_fields.append("locale")

        if updated_fields:
            user.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(user)

            # Publish user.updated event
            self.event_service.publish_user_updated(
                user_id=user_id,
                updated_fields=updated_fields
            )

        return user, updated_fields

    def get_user_preferences(self, user_id: int) -> Optional[UserPreference]:
        """
        Get user preferences

        Args:
            user_id: User ID

        Returns:
            UserPreference object or None if not found
        """
        preferences = self.db.query(UserPreference).filter(
            UserPreference.user_id == user_id
        ).first()

        # Create default preferences if not exists
        if not preferences:
            preferences = UserPreference(
                user_id=user_id,
                preferences={}
            )
            self.db.add(preferences)
            self.db.commit()
            self.db.refresh(preferences)

        return preferences

    def update_user_preferences(
        self,
        user_id: int,
        default_trading_account_id: Optional[int] = None,
        preferences: Optional[Dict[str, Any]] = None
    ) -> UserPreference:
        """
        Update user preferences

        Performs partial update - only provided fields are updated.
        Preferences dict is merged with existing preferences.

        Args:
            user_id: User ID
            default_trading_account_id: Default trading account ID (optional)
            preferences: Preferences dict to merge (optional)

        Returns:
            Updated UserPreference object

        Raises:
            ValueError: If user not found or trading account invalid
        """
        # Verify user exists
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Get or create preferences
        user_prefs = self.db.query(UserPreference).filter(
            UserPreference.user_id == user_id
        ).first()

        if not user_prefs:
            user_prefs = UserPreference(
                user_id=user_id,
                preferences={}
            )
            self.db.add(user_prefs)

        # Update default trading account
        if default_trading_account_id is not None:
            # Verify trading account exists and user has access
            account = self.db.query(TradingAccount).filter(
                TradingAccount.trading_account_id == default_trading_account_id,
                TradingAccount.user_id == user_id
            ).first()

            if not account:
                raise ValueError(
                    f"Trading account {default_trading_account_id} not found or not owned by user"
                )

            user_prefs.default_trading_account_id = default_trading_account_id

        # Merge preferences
        if preferences is not None:
            current_prefs = user_prefs.preferences or {}
            # Deep merge preferences
            merged_prefs = self._merge_preferences(current_prefs, preferences)
            user_prefs.preferences = merged_prefs

        user_prefs.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(user_prefs)

        # Publish preferences.updated event
        self.event_service.publish_preferences_updated(
            user_id=user_id,
            default_trading_account_id=user_prefs.default_trading_account_id
        )

        return user_prefs

    def _merge_preferences(
        self,
        current: Dict[str, Any],
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deep merge preference dictionaries

        Args:
            current: Current preferences
            updates: Updates to apply

        Returns:
            Merged preferences
        """
        result = current.copy()

        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dicts
                result[key] = self._merge_preferences(result[key], value)
            else:
                # Override value
                result[key] = value

        return result

    def deactivate_user(
        self,
        user_id: int,
        reason: str,
        revoke_sessions: bool = True,
        admin_id: Optional[int] = None
    ) -> Tuple[User, int]:
        """
        Deactivate user account

        Args:
            user_id: User ID to deactivate
            reason: Reason for deactivation (for audit)
            revoke_sessions: Whether to revoke all sessions
            admin_id: ID of admin performing the action

        Returns:
            Tuple of (user, sessions_revoked)

        Raises:
            ValueError: If user not found
        """
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        previous_status = user.status
        user.status = UserStatus.DEACTIVATED
        user.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(user)

        # Revoke all sessions
        sessions_revoked = 0
        if revoke_sessions:
            # TODO: Implement session revocation pattern matching
            # For now, we'd need to track sessions by user_id
            pass

        # Log deactivation event
        self._log_admin_action(
            admin_id=admin_id,
            action="user.deactivated",
            target_user_id=user_id,
            metadata={
                "previous_status": previous_status.value,
                "reason": reason,
                "sessions_revoked": sessions_revoked
            }
        )

        # Publish user.deactivated event
        self.event_service.publish_user_deactivated(
            user_id=user_id,
            reason=reason,
            deactivated_by=admin_id
        )

        return user, sessions_revoked

    def search_users(
        self,
        query: Optional[str] = None,
        status: Optional[str] = None,
        role: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[User], int]:
        """
        Search users with filters

        Args:
            query: Search query (email, name)
            status: Filter by status
            role: Filter by role
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (users, total_count)
        """
        q = self.db.query(User)

        # Apply filters
        if query:
            search_pattern = f"%{query}%"
            q = q.filter(
                or_(
                    User.email.ilike(search_pattern),
                    User.name.ilike(search_pattern)
                )
            )

        if status:
            try:
                status_enum = UserStatus(status)
                q = q.filter(User.status == status_enum)
            except ValueError:
                # Invalid status, return empty results
                return [], 0

        if role:
            # Join with roles
            q = q.join(User.roles).join(UserRole.role).filter(Role.name == role)

        # Get total count
        total = q.count()

        # Apply pagination
        offset = (page - 1) * page_size
        users = q.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()

        return users, total

    def get_user_statistics(self) -> Dict[str, int]:
        """
        Get user statistics for admin dashboard

        Returns:
            Dictionary with various user statistics
        """
        now = datetime.utcnow()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        stats = {
            "total_users": self.db.query(User).count(),
            "active_users": self.db.query(User).filter(User.status == UserStatus.ACTIVE).count(),
            "pending_verification": self.db.query(User).filter(
                User.status == UserStatus.PENDING_VERIFICATION
            ).count(),
            "suspended_users": self.db.query(User).filter(User.status == UserStatus.SUSPENDED).count(),
            "deactivated_users": self.db.query(User).filter(User.status == UserStatus.DEACTIVATED).count(),
            "users_with_mfa": self.db.query(User).filter(User.mfa_enabled == True).count(),
            "users_with_trading_accounts": self.db.query(User).join(User.trading_accounts).distinct().count(),
            "new_users_last_7_days": self.db.query(User).filter(User.created_at >= seven_days_ago).count(),
            "new_users_last_30_days": self.db.query(User).filter(User.created_at >= thirty_days_ago).count(),
        }

        return stats

    def assign_role(
        self,
        user_id: int,
        role_name: str,
        granted_by: Optional[int] = None
    ) -> User:
        """
        Assign role to user

        Args:
            user_id: User ID
            role_name: Role name (user, admin, compliance)
            granted_by: User ID who granted the role

        Returns:
            Updated user

        Raises:
            ValueError: If user or role not found, or role already assigned
        """
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        role = self.db.query(Role).filter(Role.name == role_name).first()
        if not role:
            raise ValueError(f"Role '{role_name}' not found")

        # Check if already assigned
        existing = self.db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role.role_id
        ).first()

        if existing:
            raise ValueError(f"User already has role '{role_name}'")

        # Assign role
        user_role = UserRole(
            user_id=user_id,
            role_id=role.role_id,
            granted_by=granted_by
        )

        self.db.add(user_role)
        self.db.commit()
        self.db.refresh(user)

        # Invalidate authorization cache
        self.redis.invalidate_authz_cache(subject=f"user:{user_id}")

        # Log admin action
        self._log_admin_action(
            admin_id=granted_by,
            action="role.assigned",
            target_user_id=user_id,
            metadata={"role": role_name}
        )

        # Publish role.assigned event
        current_roles = [ur.role.name for ur in user.roles]
        self.event_service.publish_role_assigned(
            user_id=user_id,
            role_name=role_name,
            granted_by=granted_by,
            current_roles=current_roles
        )

        return user

    def revoke_role(
        self,
        user_id: int,
        role_name: str,
        revoked_by: Optional[int] = None
    ) -> User:
        """
        Revoke role from user

        Args:
            user_id: User ID
            role_name: Role name to revoke
            revoked_by: User ID who revoked the role

        Returns:
            Updated user

        Raises:
            ValueError: If user or role not found, or role not assigned
        """
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        role = self.db.query(Role).filter(Role.name == role_name).first()
        if not role:
            raise ValueError(f"Role '{role_name}' not found")

        # Find user role
        user_role = self.db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role.role_id
        ).first()

        if not user_role:
            raise ValueError(f"User does not have role '{role_name}'")

        # Prevent revoking last role
        role_count = self.db.query(UserRole).filter(UserRole.user_id == user_id).count()
        if role_count == 1:
            raise ValueError("Cannot revoke last role from user")

        self.db.delete(user_role)
        self.db.commit()
        self.db.refresh(user)

        # Invalidate authorization cache
        self.redis.invalidate_authz_cache(subject=f"user:{user_id}")

        # Log admin action
        self._log_admin_action(
            admin_id=revoked_by,
            action="role.revoked",
            target_user_id=user_id,
            metadata={"role": role_name}
        )

        # Publish role.revoked event
        current_roles = [ur.role.name for ur in user.roles]
        self.event_service.publish_role_revoked(
            user_id=user_id,
            role_name=role_name,
            revoked_by=revoked_by,
            current_roles=current_roles
        )

        return user

    def _log_admin_action(
        self,
        admin_id: Optional[int],
        action: str,
        target_user_id: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log admin action to audit trail

        Args:
            admin_id: Admin user ID who performed the action
            action: Action type
            target_user_id: Target user ID
            metadata: Additional metadata
        """
        event = AuthEvent(
            user_id=admin_id,
            event_type=action,
            metadata={
                **(metadata or {}),
                "target_user_id": target_user_id
            }
        )

        self.db.add(event)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()

    def _publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Publish event to Redis pub/sub

        Args:
            event_type: Event type
            data: Event data
        """
        # TODO: Implement event publishing
        # self.redis.publish_json(f"events:{event_type}", data)
        pass
