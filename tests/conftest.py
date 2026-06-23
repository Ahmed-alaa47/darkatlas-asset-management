import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Asset, AssetRelationship

TEST_DB_URL = "sqlite:///./test_darkatlas.db"  # use sqlite for tests


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def sample_assets():
    return [
        {"id": "a1", "type": "domain", "value": "example.com",
         "status": "active", "source": "scan", "tags": ["root"], "metadata": {}},
        {"id": "a2", "type": "subdomain", "value": "api.example.com",
         "status": "active", "source": "scan", "tags": ["prod"],
         "metadata": {}, "parent": "a1"},
        {"id": "a3", "type": "certificate", "value": "CN=api.example.com",
         "status": "active", "source": "scan", "tags": [],
         "metadata": {"issuer": "Let's Encrypt",
                      "expires": "2025-01-02"},
         "covers": "a2"},
        {"id": "a4", "type": "service", "value": "22/tcp",
         "status": "active", "source": "scan", "tags": [],
         "metadata": {"banner": "OpenSSH 7.4"}},
        {"id": "a5", "type": "technology", "value": "nginx",
         "status": "active", "source": "scan", "tags": [],
         "metadata": {"version": "1.10.3"}},
    ]