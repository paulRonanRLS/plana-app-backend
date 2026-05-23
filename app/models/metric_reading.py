import enum

from sqlalchemy import BigInteger, Column, DateTime, Enum, Float, Index, PrimaryKeyConstraint, Text
from sqlalchemy.schema import FetchedValue

from app.database import Base


class MetricType(str, enum.Enum):
    hrv = "hrv"
    sleep_score = "sleep_score"
    sleep_duration_hours = "sleep_duration_hours"
    resting_hr = "resting_hr"
    body_battery = "body_battery"
    tss = "tss"
    weight = "weight"
    subjective_feel = "subjective_feel"   # -1=flat, 0=neutral, 1=good
    alcohol_units = "alcohol_units"
    physical_state = "physical_state"     # text_value carries the description
    illness_log = "illness_log"           # text_value carries start/recovery note


class MetricSource(str, enum.Enum):
    garmin = "garmin"
    strava = "strava"
    manual = "manual"
    telegram = "telegram"


class MetricReading(Base):
    """Time series table — registered as a TimescaleDB hypertable on timestamp."""

    __tablename__ = "metric_readings"
    __table_args__ = (
        # TimescaleDB requires the partition column (timestamp) in every unique constraint.
        PrimaryKeyConstraint("id", "timestamp"),
        Index("ix_metric_readings_type_ts", "metric_type", "timestamp"),
    )

    # server_default=FetchedValue() tells SQLAlchemy the sequence value comes from
    # PostgreSQL (nextval on metric_readings_id_seq); avoids autoincrement=True which
    # SQLite rejects on composite PKs.
    id = Column(BigInteger, server_default=FetchedValue(), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    metric_type = Column(Enum(MetricType), nullable=False)
    value = Column(Float, nullable=True)        # numeric reading; null for text-only metrics
    text_value = Column(Text, nullable=True)    # for physical_state and illness_log entries
    source = Column(Enum(MetricSource), nullable=False)
    notes = Column(Text, nullable=True)
