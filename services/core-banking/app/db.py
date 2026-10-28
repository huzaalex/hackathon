import os
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

engine = create_engine(os.environ.get("DATABASE_URL", "sqlite:///./bank.db"), pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

Money = Numeric(14, 2)


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    cnp: Mapped[str] = mapped_column(String(13), index=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    birth_date: Mapped[str] = mapped_column(String(10))
    address: Mapped[str] = mapped_column(String(255))


class Account(Base):
    __tablename__ = "accounts"
    iban: Mapped[str] = mapped_column(String(34), primary_key=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    product: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16))  # ACTIVE | CLOSED
    balance: Mapped[Decimal] = mapped_column(Money)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    iban: Mapped[str] = mapped_column(ForeignKey("accounts.iban"), index=True)
    booked_at: Mapped[datetime] = mapped_column(DateTime)
    amount: Mapped[Decimal] = mapped_column(Money)
    direction: Mapped[str] = mapped_column(String(6))  # CREDIT | DEBIT
    source: Mapped[str] = mapped_column(String(40))  # SALARY, PENSION, CHILD_ALLOWANCE, SOCIAL_BENEFIT, TRANSFER, PAYMENT...
    description: Mapped[str] = mapped_column(String(255))


class Garnishment(Base):
    """A garnishment order (poprire) registered at the bank."""
    __tablename__ = "garnishments"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    case_ref: Mapped[str] = mapped_column(String(80), index=True)
    case_ref_norm: Mapped[str] = mapped_column(String(80), index=True)
    issuer_type: Mapped[str] = mapped_column(String(32))  # BAILIFF | TAX_AUTHORITY | LOCAL_TAX_AUTHORITY | OTHER
    issuer_name: Mapped[str] = mapped_column(String(160))
    creditor: Mapped[str] = mapped_column(String(160))
    claim_type: Mapped[str] = mapped_column(String(24))
    total_amount: Mapped[Decimal] = mapped_column(Money)  # RON
    transferred_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    received_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16))  # ACTIVE | LIFTED | SATISFIED
    document_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Hold(Base):
    """Amount made unavailable (indisponibilizat) on an account for a garnishment."""
    __tablename__ = "holds"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    iban: Mapped[str] = mapped_column(ForeignKey("accounts.iban"), index=True)
    garnishment_id: Mapped[str] = mapped_column(ForeignKey("garnishments.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)  # account currency
    amount_ron: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(16))  # ACTIVE | RELEASED
    created_at: Mapped[datetime] = mapped_column(DateTime)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
