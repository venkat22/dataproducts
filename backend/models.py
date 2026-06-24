from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class DataProduct(Base):
    __tablename__ = "data_products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    domain = Column(String(100), nullable=False, default="")
    owner_name = Column(String(200), nullable=False, default="")
    owner_email = Column(String(200), nullable=False, default="")
    classification = Column(String(50), nullable=False, default="Internal")
    source_systems = Column(Text, nullable=False, default="")  # comma-separated
    update_frequency = Column(String(50), nullable=False, default="Daily")
    output_format = Column(String(50), nullable=False, default="Table")
    sla = Column(String(200), nullable=False, default="")
    contains_pii = Column(Boolean, nullable=False, default=False)
    tags = Column(Text, nullable=False, default="")  # comma-separated
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
