from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.keitaro import keitaro
from app.main import app
from app import main


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    original_session_local = main.SessionLocal
    main.SessionLocal = TestingSession
    original_keitaro_configured = keitaro.configured
    keitaro.configured = False
    main._last_keitaro_sync = 0.0
    main._last_keitaro_sync_at = None
    main._sync_in_progress = False
    main._sync_error = None
    main._sync_task = None
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        keitaro.configured = original_keitaro_configured
        main.SessionLocal = original_session_local
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
