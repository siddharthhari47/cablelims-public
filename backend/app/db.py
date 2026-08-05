"""
Database engine/session setup.

MVP note: single SQLite file, WAL mode enabled for reasonable concurrent
read/write from multiple Scientific Assistant phones + one Scientist desktop
client on the lab LAN. Swap the URL for Postgres later with no code changes
elsewhere -- nothing outside this module knows which DB engine is in use.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "cablelims.db")

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    # Without this, a writer that finds the database locked (e.g. two
    # requests both allocating a sequence number at once -- see
    # services/sequence_service.py) fails immediately with "database is
    # locked" instead of waiting briefly for the other transaction to
    # commit. 5s (H14: Settings-configurable) comfortably covers this app's
    # actual concurrency (a handful of lab devices, not a high-throughput
    # service).
    cursor.execute(f"PRAGMA busy_timeout={settings.db_busy_timeout_ms}")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
