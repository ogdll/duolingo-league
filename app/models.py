from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, JSON, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    duolingo_username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    real_name: Mapped[str] = mapped_column(String, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    snapshots: Mapped[list["StatsSnapshot"]] = relationship(back_populates="user")


class StatsSnapshot(Base):
    __tablename__ = "stats_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[datetime] = mapped_column(Date, nullable=False)
    xp_total: Mapped[int] = mapped_column(Integer, nullable=False)
    xp_gained_today: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    league: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    languages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="snapshots")
