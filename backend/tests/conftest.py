import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.engine import Mnemos  # noqa: E402
from app.services.decision import Candidate  # noqa: E402


@pytest.fixture
def engine(tmp_path):
    e = Mnemos(Settings(data_dir=tmp_path / "data"))
    yield e
    e.close()


@pytest.fixture
def ingest(engine):
    def _ingest(text, **kw):
        kw.setdefault("source_type", "user")
        return engine.memory.ingest(Candidate(content=text, **kw))
    return _ingest


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.delenv("MNEMOS_API_KEY", raising=False)
    e = Mnemos(Settings(data_dir=tmp_path / "api"))
    main.set_engine(e)
    with TestClient(main.app) as c:
        yield c
    main.set_engine(None)
    e.close()
