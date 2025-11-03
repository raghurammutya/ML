"""
Auth Event model for audit logging (TimescaleDB hypertable)
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID, INET
import uuid

from app.core.database import Base


class AuthEvent(Base):
    """Auth Event model for audit logging - TimescaleDB hypertable"""
    __tablename__ = "auth_events"
    __table_args__ = (
        Index('idx_auth_events_user_id', 'user_id', 'timestamp'),
        Index('idx_auth_events_type', 'event_type', 'timestamp'),
        Index('idx_auth_events_session', 'session_id', 'timestamp'),
        Index('idx_auth_events_risk', 'risk_score', postgresql_where=Column('risk_score') == 'high'),
    )

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(100), nullable=False)  # 'login.success', 'login.failed', etc.
    ip = Column(INET, nullable=True)
    country = Column(String(2), nullable=True)  # ISO country code
    device_fingerprint = Column(String(255), nullable=True)
    session_id = Column(String(255), nullable=True, index=True)
    metadata = Column(JSONB, nullable=True)
    risk_score = Column(String(20), nullable=True)  # 'low', 'medium', 'high'
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    notification_sent = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<AuthEvent(event_id='{self.event_id}', type='{self.event_type}', user_id={self.user_id})>"
