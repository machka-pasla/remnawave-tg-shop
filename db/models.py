from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, ForeignKey, UniqueConstraint, Text, BigInteger
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.sql import func
from datetime import datetime


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String, nullable=True, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    language_code = Column(String, default="ru")
    registration_date = Column(DateTime(timezone=True),
                               server_default=func.now())
    is_banned = Column(Boolean, default=False)
    panel_user_uuid = Column(String, nullable=True, unique=True, index=True)
    referred_by_id = Column(BigInteger,
                            ForeignKey("users.user_id"),
                            nullable=True)

    referrer = relationship("User", remote_side=[user_id], backref="referrals")
    subscriptions = relationship("Subscription",
                                 back_populates="user",
                                 cascade="all, delete-orphan")
    payments = relationship("Payment",
                            back_populates="user",
                            cascade="all, delete-orphan")
    promo_code_activations = relationship("PromoCodeActivation",
                                          back_populates="user",
                                          cascade="all, delete-orphan")
    message_logs_authored = relationship("MessageLog",
                                         foreign_keys="MessageLog.user_id",
                                         back_populates="author_user",
                                         cascade="all, delete-orphan")
    message_logs_targeted = relationship(
        "MessageLog",
        foreign_keys="MessageLog.target_user_id",
        back_populates="target_user",
        cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(user_id={self.user_id}, username='{self.username}')>"


class Subscription(Base):
    __tablename__ = "subscriptions"

    subscription_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger,
                     ForeignKey("users.user_id"),
                     nullable=False,
                     index=True)
    panel_user_uuid = Column(String, nullable=False, index=True)
    panel_subscription_uuid = Column(String,
                                     unique=True,
                                     index=True,
                                     nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_months = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    status_from_panel = Column(String, nullable=True)
    traffic_limit_bytes = Column(BigInteger, nullable=True)
    traffic_used_bytes = Column(BigInteger, nullable=True)
    last_notification_sent = Column(DateTime(timezone=True), nullable=True)
    provider = Column(String, nullable=True)
    skip_notifications = Column(Boolean, default=False)

    user = relationship("User", back_populates="subscriptions")

    def __repr__(self):
        return f"<Subscription(id={self.subscription_id}, user_id={self.user_id}, panel_uuid='{self.panel_user_uuid}', ends='{self.end_date}')>"


class Payment(Base):
    __tablename__ = "payments"

    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger,
                     ForeignKey("users.user_id"),
                     nullable=False,
                     index=True)
    yookassa_payment_id = Column(String,
                                 unique=True,
                                 index=True,
                                 nullable=True)
    provider_payment_id = Column(String, unique=True, nullable=True)
    provider = Column(String, nullable=False, default="yookassa", index=True)
    idempotence_key = Column(String, unique=True, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    subscription_duration_months = Column(Integer, nullable=True)
    promo_code_id = Column(Integer,
                           ForeignKey("promo_codes.promo_code_id"),
                           nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        onupdate=func.now(),
                        nullable=True)

    user = relationship("User", back_populates="payments")
    promo_code_used = relationship("PromoCode",
                                   back_populates="payments_where_used")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    promo_code_id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False, index=True)
    bonus_days = Column(Integer, nullable=False)
    max_activations = Column(Integer, nullable=False)
    current_activations = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_by_admin_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True)

    activations = relationship("PromoCodeActivation",
                               back_populates="promo_code",
                               cascade="all, delete-orphan")
    payments_where_used = relationship("Payment",
                                       back_populates="promo_code_used")


class PromoCodeActivation(Base):
    __tablename__ = "promo_code_activations"

    activation_id = Column(Integer, primary_key=True, autoincrement=True)
    promo_code_id = Column(Integer,
                           ForeignKey("promo_codes.promo_code_id"),
                           nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    activated_at = Column(DateTime(timezone=True), server_default=func.now())
    payment_id = Column(Integer,
                        ForeignKey("payments.payment_id"),
                        nullable=True)

    promo_code = relationship("PromoCode", back_populates="activations")
    user = relationship("User", back_populates="promo_code_activations")
    payment = relationship("Payment")

    __table_args__ = (UniqueConstraint('promo_code_id',
                                       'user_id',
                                       name='uq_promo_user_activation'), )


class MessageLog(Base):
    __tablename__ = "message_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger,
                     ForeignKey("users.user_id"),
                     nullable=True,
                     index=True)
    telegram_username = Column(String, nullable=True)
    telegram_first_name = Column(String, nullable=True)
    event_type = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=True)
    raw_update_preview = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True),
                       server_default=func.now(),
                       index=True)
    is_admin_event = Column(Boolean, default=False)
    target_user_id = Column(BigInteger,
                            ForeignKey("users.user_id"),
                            nullable=True,
                            index=True)

    author_user = relationship("User",
                               foreign_keys=[user_id],
                               back_populates="message_logs_authored")
    target_user = relationship("User",
                               foreign_keys=[target_user_id],
                               back_populates="message_logs_targeted")


class PanelSyncStatus(Base):
    __tablename__ = "panel_sync_status"

    id = Column(Integer, primary_key=True, default=1, autoincrement=False)
    last_sync_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    users_processed_from_panel = Column(Integer, default=0)
    subscriptions_synced = Column(Integer, default=0)

    __table_args__ = (UniqueConstraint('id'), )
