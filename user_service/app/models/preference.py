"""
User Preference model
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserPreference(Base):
    """User Preferences model"""
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint('user_id', name='uq_user_preference'),
        Index('idx_user_preferences_user_id', 'user_id'),
        Index('idx_user_preferences_jsonb', 'preferences', postgresql_using='gin'),
    )

    preference_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    preferences = Column(JSONB, nullable=False, default={})
    default_trading_account_id = Column(BigInteger, nullable=True)  # FK will be added via migration
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="preferences")

    def __repr__(self):
        return f"<UserPreference(user_id={self.user_id})>"
