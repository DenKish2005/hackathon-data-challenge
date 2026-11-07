import pytest

from cqa.backend.database import Database


@pytest.fixture
def database(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'foundation.db'}")
    db.initialize()
    yield db
    db.engine.dispose()
