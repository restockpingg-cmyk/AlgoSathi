from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from algosathi.core.enums import Mode
from algosathi.core.models import Fill
from algosathi.persistence.models import Base, Trade

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_DB_PATH = DATA_DIR / "algosathi.db"


def get_engine(db_path: Path = DEFAULT_DB_PATH):
    DATA_DIR.mkdir(exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    return engine


def _add_missing_columns(engine) -> None:
    """create_all creates missing tables but never alters existing ones, so a database written
    before a column existed keeps working until something reads that column and fails. Only
    additive, nullable-with-default columns belong here."""
    with engine.begin() as connection:
        existing = {row[1] for row in connection.execute(text("PRAGMA table_info(trades)"))}
        if existing and "charges" not in existing:
            connection.execute(text("ALTER TABLE trades ADD COLUMN charges FLOAT DEFAULT 0.0"))


def get_session_factory(db_path: Path = DEFAULT_DB_PATH) -> sessionmaker[Session]:
    engine = get_engine(db_path)
    return sessionmaker(bind=engine)


def record_fill(session_factory: sessionmaker[Session], fill: Fill, mode: Mode) -> None:
    with session_factory() as session:
        session.add(
            Trade(
                order_id=fill.order_id,
                symbol=fill.symbol,
                side=fill.side.value,
                quantity=fill.quantity,
                price=fill.price,
                timestamp=fill.timestamp,
                mode=mode.value,
                charges=fill.charges,
            )
        )
        session.commit()


def all_trades(session_factory: sessionmaker[Session]) -> list[Trade]:
    with session_factory() as session:
        return list(session.query(Trade).order_by(Trade.timestamp).all())
