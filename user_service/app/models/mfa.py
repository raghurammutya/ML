"""
MFA (Multi-Factor Authentication) models
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class MfaTotp(Base):
    """MFA TOTP model - Time-based One-Time Password"""
    __tablename__ = "mfa_totp"
    __table_args__ = (
        UniqueConstraint('user_id', name='uq_mfa_totp_user'),
    )

    totp_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    secret_encrypted = Column(Text, nullable=False)  # Encrypted TOTP seed
    backup_codes_encrypted = Column(JSONB, nullable=False)  # Encrypted backup codes (hashed)
    verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    verified_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="mfa_totp")

    def __repr__(self):
        return f"<MfaTotp(user_id={self.user_id}, verified={self.verified})>"
