"""
Trading Account Service

Manages broker account linking, credential encryption, and shared access.

Security:
- All credentials (API keys, secrets, tokens) are encrypted with KMS
- Only owners can rotate credentials or grant/revoke memberships
- Membership permissions control access levels
"""

from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.config import settings
from app.core.redis_client import RedisClient
from app.models import User, TradingAccount, TradingAccountMembership, TradingAccountStatus
from app.services.event_service import EventService


class TradingAccountService:
    """Service for trading account management"""

    def __init__(self, db: Session, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.event_service = EventService(redis)

    def link_trading_account(
        self,
        user_id: int,
        broker: str,
        broker_user_id: str,
        api_key: str,
        api_secret: str,
        access_token: Optional[str] = None,
        account_name: Optional[str] = None
    ) -> TradingAccount:
        """
        Link a new trading account to user

        Args:
            user_id: User ID (will become owner)
            broker: Broker type (kite, upstox, etc.)
            broker_user_id: Broker's user ID
            api_key: API key from broker
            api_secret: API secret from broker
            access_token: Access token (optional)
            account_name: Friendly name for account

        Returns:
            TradingAccount object

        Raises:
            ValueError: If user not found or account already linked
        """
        # Verify user exists
        user = self.db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Check if account already linked
        existing = self.db.query(TradingAccount).filter(
            TradingAccount.broker == broker,
            TradingAccount.broker_user_id == broker_user_id
        ).first()

        if existing:
            raise ValueError(
                f"Trading account {broker}:{broker_user_id} is already linked "
                f"(owned by user {existing.user_id})"
            )

        # Encrypt credentials with KMS
        encrypted_api_key = self._encrypt_credential(api_key)
        encrypted_api_secret = self._encrypt_credential(api_secret)
        encrypted_access_token = self._encrypt_credential(access_token) if access_token else None

        # Create trading account
        account = TradingAccount(
            user_id=user_id,
            broker=broker,
            broker_user_id=broker_user_id,
            api_key_encrypted=encrypted_api_key,
            api_secret_encrypted=encrypted_api_secret,
            access_token_encrypted=encrypted_access_token,
            account_name=account_name,
            status=TradingAccountStatus.ACTIVE
        )

        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)

        # Publish trading_account.linked event
        self.event_service.publish_trading_account_linked(
            user_id=user_id,
            trading_account_id=account.trading_account_id,
            broker=broker
        )

        return account

    def get_user_trading_accounts(
        self,
        user_id: int
    ) -> Tuple[List[TradingAccount], List[Tuple[TradingAccount, TradingAccountMembership]]]:
        """
        Get all trading accounts accessible to user

        Returns owned accounts and shared accounts separately.

        Args:
            user_id: User ID

        Returns:
            Tuple of (owned_accounts, shared_accounts_with_memberships)
        """
        # Get owned accounts
        owned_accounts = self.db.query(TradingAccount).filter(
            TradingAccount.user_id == user_id
        ).order_by(TradingAccount.created_at.desc()).all()

        # Get shared accounts (via memberships)
        shared_query = self.db.query(TradingAccount, TradingAccountMembership).join(
            TradingAccountMembership,
            TradingAccount.trading_account_id == TradingAccountMembership.trading_account_id
        ).filter(
            TradingAccountMembership.user_id == user_id
        ).order_by(TradingAccountMembership.granted_at.desc()).all()

        return owned_accounts, shared_query

    def unlink_trading_account(
        self,
        trading_account_id: int,
        user_id: int
    ) -> int:
        """
        Unlink (delete) trading account

        Only owner can unlink. All memberships are revoked.

        Args:
            trading_account_id: Trading account ID
            user_id: User ID (must be owner)

        Returns:
            Number of memberships revoked

        Raises:
            ValueError: If account not found or user is not owner
        """
        account = self.db.query(TradingAccount).filter(
            TradingAccount.trading_account_id == trading_account_id
        ).first()

        if not account:
            raise ValueError(f"Trading account {trading_account_id} not found")

        if account.user_id != user_id:
            raise ValueError(
                f"Only owner (user {account.user_id}) can unlink this account"
            )

        # Count memberships to be revoked
        memberships_count = self.db.query(TradingAccountMembership).filter(
            TradingAccountMembership.trading_account_id == trading_account_id
        ).count()

        # Delete memberships
        self.db.query(TradingAccountMembership).filter(
            TradingAccountMembership.trading_account_id == trading_account_id
        ).delete()

        # Delete account
        self.db.delete(account)
        self.db.commit()

        # Publish trading_account.unlinked event
        self.event_service.publish_trading_account_unlinked(
            user_id=user_id,
            trading_account_id=trading_account_id,
            broker=account.broker
        )

        return memberships_count

    def rotate_credentials(
        self,
        trading_account_id: int,
        user_id: int,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> TradingAccount:
        """
        Rotate API credentials for trading account

        Only owner can rotate credentials.

        Args:
            trading_account_id: Trading account ID
            user_id: User ID (must be owner)
            api_key: New API key (optional)
            api_secret: New API secret (optional)
            access_token: New access token (optional)

        Returns:
            Updated TradingAccount

        Raises:
            ValueError: If account not found or user is not owner
        """
        account = self.db.query(TradingAccount).filter(
            TradingAccount.trading_account_id == trading_account_id
        ).first()

        if not account:
            raise ValueError(f"Trading account {trading_account_id} not found")

        if account.user_id != user_id:
            raise ValueError(
                f"Only owner (user {account.user_id}) can rotate credentials"
            )

        # Update credentials (encrypt if provided)
        if api_key is not None:
            account.api_key_encrypted = self._encrypt_credential(api_key)

        if api_secret is not None:
            account.api_secret_encrypted = self._encrypt_credential(api_secret)

        if access_token is not None:
            account.access_token_encrypted = self._encrypt_credential(access_token)

        account.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(account)

        return account

    def grant_membership(
        self,
        trading_account_id: int,
        owner_id: int,
        member_email: str,
        permissions: List[str],
        note: Optional[str] = None
    ) -> TradingAccountMembership:
        """
        Grant shared access to trading account

        Only owner can grant memberships.

        Args:
            trading_account_id: Trading account ID
            owner_id: Owner's user ID
            member_email: Email of user to grant access to
            permissions: List of permissions (view, trade, manage)
            note: Optional note

        Returns:
            TradingAccountMembership object

        Raises:
            ValueError: If account not found, user is not owner, or member not found
        """
        # Verify account and ownership
        account = self.db.query(TradingAccount).filter(
            TradingAccount.trading_account_id == trading_account_id
        ).first()

        if not account:
            raise ValueError(f"Trading account {trading_account_id} not found")

        if account.user_id != owner_id:
            raise ValueError(
                f"Only owner (user {account.user_id}) can grant memberships"
            )

        # Find member by email
        member = self.db.query(User).filter(User.email == member_email).first()
        if not member:
            raise ValueError(f"User with email {member_email} not found")

        # Check if member is owner
        if member.user_id == owner_id:
            raise ValueError("Cannot grant membership to account owner")

        # Check if membership already exists
        existing = self.db.query(TradingAccountMembership).filter(
            TradingAccountMembership.trading_account_id == trading_account_id,
            TradingAccountMembership.user_id == member.user_id
        ).first()

        if existing:
            raise ValueError(
                f"User {member_email} already has access to this account"
            )

        # Create membership
        membership = TradingAccountMembership(
            trading_account_id=trading_account_id,
            user_id=member.user_id,
            permissions=permissions,
            granted_by=owner_id,
            note=note
        )

        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)

        # Publish membership.granted event
        self.event_service.publish_membership_granted(
            user_id=member.user_id,
            trading_account_id=trading_account_id,
            membership_id=membership.membership_id,
            permissions=permissions,
            granted_by=owner_id
        )

        return membership

    def revoke_membership(
        self,
        trading_account_id: int,
        membership_id: int,
        revoker_id: int
    ) -> TradingAccountMembership:
        """
        Revoke shared access to trading account

        Only owner can revoke memberships.

        Args:
            trading_account_id: Trading account ID
            membership_id: Membership ID to revoke
            revoker_id: User ID revoking (must be owner)

        Returns:
            Revoked membership object

        Raises:
            ValueError: If membership not found or user is not owner
        """
        # Verify account and ownership
        account = self.db.query(TradingAccount).filter(
            TradingAccount.trading_account_id == trading_account_id
        ).first()

        if not account:
            raise ValueError(f"Trading account {trading_account_id} not found")

        if account.user_id != revoker_id:
            raise ValueError(
                f"Only owner (user {account.user_id}) can revoke memberships"
            )

        # Find membership
        membership = self.db.query(TradingAccountMembership).filter(
            TradingAccountMembership.membership_id == membership_id,
            TradingAccountMembership.trading_account_id == trading_account_id
        ).first()

        if not membership:
            raise ValueError(
                f"Membership {membership_id} not found for account {trading_account_id}"
            )

        member_id = membership.user_id
        self.db.delete(membership)
        self.db.commit()

        # Publish membership.revoked event
        self.event_service.publish_membership_revoked(
            user_id=member_id,
            trading_account_id=trading_account_id,
            membership_id=membership_id,
            revoked_by=revoker_id
        )

        return membership

    def get_memberships(
        self,
        trading_account_id: int,
        owner_id: int
    ) -> List[TradingAccountMembership]:
        """
        Get all memberships for trading account

        Only owner can view memberships.

        Args:
            trading_account_id: Trading account ID
            owner_id: Owner's user ID

        Returns:
            List of memberships

        Raises:
            ValueError: If account not found or user is not owner
        """
        # Verify account and ownership
        account = self.db.query(TradingAccount).filter(
            TradingAccount.trading_account_id == trading_account_id
        ).first()

        if not account:
            raise ValueError(f"Trading account {trading_account_id} not found")

        if account.user_id != owner_id:
            raise ValueError(
                f"Only owner (user {account.user_id}) can view memberships"
            )

        # Get memberships with user info
        memberships = self.db.query(TradingAccountMembership).filter(
            TradingAccountMembership.trading_account_id == trading_account_id
        ).order_by(TradingAccountMembership.granted_at.desc()).all()

        return memberships

    def check_access(
        self,
        trading_account_id: int,
        user_id: int,
        required_permissions: Optional[List[str]] = None
    ) -> Tuple[bool, bool, List[str]]:
        """
        Check user's access to trading account

        Args:
            trading_account_id: Trading account ID
            user_id: User ID
            required_permissions: Required permissions (optional)

        Returns:
            Tuple of (has_access: bool, is_owner: bool, actual_permissions: List[str])
        """
        # Check if user is owner
        account = self.db.query(TradingAccount).filter(
            TradingAccount.trading_account_id == trading_account_id
        ).first()

        if not account:
            return False, False, []

        if account.user_id == user_id:
            # Owner has all permissions
            all_perms = ["view", "trade", "manage"]
            if required_permissions:
                has_required = all(perm in all_perms for perm in required_permissions)
                return has_required, True, all_perms
            return True, True, all_perms

        # Check membership
        membership = self.db.query(TradingAccountMembership).filter(
            TradingAccountMembership.trading_account_id == trading_account_id,
            TradingAccountMembership.user_id == user_id
        ).first()

        if not membership:
            return False, False, []

        actual_perms = membership.permissions or []

        if required_permissions:
            has_required = all(perm in actual_perms for perm in required_permissions)
            return has_required, False, actual_perms

        return True, False, actual_perms

    def get_decrypted_credentials(
        self,
        trading_account_id: int,
        requesting_service: str
    ) -> Dict[str, Any]:
        """
        Get decrypted credentials for trading account

        INTERNAL USE ONLY - for service-to-service communication.

        Args:
            trading_account_id: Trading account ID
            requesting_service: Name of service requesting credentials (for audit)

        Returns:
            Dict with decrypted credentials

        Raises:
            ValueError: If account not found

        Security:
            - Should only be called by internal/authorized services
            - Log all credential access for audit
            - Never expose via public API
        """
        account = self.db.query(TradingAccount).filter(
            TradingAccount.trading_account_id == trading_account_id
        ).first()

        if not account:
            raise ValueError(f"Trading account {trading_account_id} not found")

        # Decrypt credentials
        api_key = self._decrypt_credential(account.api_key_encrypted)
        api_secret = self._decrypt_credential(account.api_secret_encrypted)
        access_token = (
            self._decrypt_credential(account.access_token_encrypted)
            if account.access_token_encrypted
            else None
        )

        # TODO: Log credential access to audit trail
        # self._log_credential_access(
        #     trading_account_id=trading_account_id,
        #     requesting_service=requesting_service
        # )

        return {
            "trading_account_id": trading_account_id,
            "broker": account.broker,
            "broker_user_id": account.broker_user_id,
            "api_key": api_key,
            "api_secret": api_secret,
            "access_token": access_token,
            "status": account.status.value
        }

    def _encrypt_credential(self, plaintext: str) -> str:
        """
        Encrypt credential with KMS

        TODO: Implement actual KMS encryption
        For now, storing plaintext (DEVELOPMENT ONLY)

        Args:
            plaintext: Plain text credential

        Returns:
            Encrypted credential (base64)

        Production Implementation:
            - Use AWS KMS, Google Cloud KMS, or HashiCorp Vault
            - Example with AWS KMS:
                import boto3
                kms = boto3.client('kms')
                response = kms.encrypt(
                    KeyId=settings.KMS_KEY_ID,
                    Plaintext=plaintext.encode()
                )
                return base64.b64encode(response['CiphertextBlob']).decode()
        """
        # DEVELOPMENT ONLY - Store plaintext
        # TODO: Replace with actual KMS encryption before production
        import base64
        return base64.b64encode(plaintext.encode()).decode()

    def _decrypt_credential(self, encrypted: str) -> str:
        """
        Decrypt credential with KMS

        TODO: Implement actual KMS decryption
        For now, decoding base64 (DEVELOPMENT ONLY)

        Args:
            encrypted: Encrypted credential (base64)

        Returns:
            Decrypted plaintext credential

        Production Implementation:
            - Use AWS KMS, Google Cloud KMS, or HashiCorp Vault
            - Example with AWS KMS:
                import boto3
                import base64
                kms = boto3.client('kms')
                ciphertext_blob = base64.b64decode(encrypted)
                response = kms.decrypt(CiphertextBlob=ciphertext_blob)
                return response['Plaintext'].decode()
        """
        # DEVELOPMENT ONLY - Decode base64
        # TODO: Replace with actual KMS decryption before production
        import base64
        return base64.b64decode(encrypted.encode()).decode()
