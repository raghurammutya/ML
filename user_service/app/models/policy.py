"""
Policy model for authorization (ABAC)
"""

from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Text, Index
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class PolicyEffect(str, enum.Enum):
    """Policy effect"""
    ALLOW = "allow"
    DENY = "deny"


class Policy(Base):
    """Authorization Policy model for ABAC"""
    __tablename__ = "policies"
    __table_args__ = (
        Index('idx_policies_enabled', 'enabled'),
    )

    policy_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    effect = Column(Enum(PolicyEffect), default=PolicyEffect.ALLOW, nullable=False)
    subjects = Column(JSONB, nullable=False)  # ['user:*', 'role:admin']
    actions = Column(JSONB, nullable=False)   # ['trade:*', 'read:account']
    resources = Column(JSONB, nullable=False)  # ['trading_account:*']
    conditions = Column(JSONB, nullable=False, default={})  # {"owner": true, "account_active": true}
    priority = Column(Integer, default=0, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Policy(id={self.policy_id}, name='{self.name}', effect='{self.effect}')>"
