"""SQLAlchemy sessions; file SQLite by default, configurable for PostgreSQL."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cqa.backend.models import Base


class Database:
    def __init__(self, url):
        parsed = make_url(url)
        kwargs = {}
        if parsed.get_backend_name() == "sqlite":
            if parsed.database and parsed.database != ":memory:":
                Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
            else:
                kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
        self.engine = create_engine(url, **kwargs)
        if parsed.get_backend_name() == "sqlite":

            @event.listens_for(self.engine, "connect")
            def pragmas(connection, record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self):
        Base.metadata.create_all(self.engine)
