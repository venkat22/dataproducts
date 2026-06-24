import time

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Wait for the database to be reachable, then create tables."""
    import models  # noqa: F401  (register models on Base)

    last_error = None
    for attempt in range(1, settings.db_connect_retries + 1):
        try:
            with engine.connect():
                pass
            Base.metadata.create_all(bind=engine)
            return
        except OperationalError as exc:  # database not ready yet
            last_error = exc
            print(f"[db] not ready (attempt {attempt}), retrying...", flush=True)
            time.sleep(settings.db_connect_delay_seconds)
    raise RuntimeError(f"Could not connect to database: {last_error}")
