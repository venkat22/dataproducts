from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

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

    contract = relationship(
        "DataContract",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def has_contract(self) -> bool:
        return self.contract is not None


class DataContract(Base):
    """A lightweight, versioned interface contract for a data product.

    Loosely aligned with the Open Data Contract Standard (ODCS): a schema
    (fields), quality expectations, and service-level objectives.
    """

    __tablename__ = "data_contracts"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    version = Column(String(50), nullable=False, default="1.0.0")
    status = Column(String(50), nullable=False, default="draft")  # draft/active/deprecated

    # [{name, type, required, pii, description}]
    schema_fields = Column(JSON, nullable=False, default=list)
    # [{field, rule, description}]
    quality_rules = Column(JSON, nullable=False, default=list)

    slo_availability = Column(String(100), nullable=False, default="")
    slo_freshness = Column(String(200), nullable=False, default="")
    slo_max_latency = Column(String(100), nullable=False, default="")

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    product = relationship("DataProduct", back_populates="contract")
