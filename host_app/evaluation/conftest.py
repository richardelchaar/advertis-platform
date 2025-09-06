"""
conftest.py

Pytest configuration and fixtures for host_app tests.
Provides database session management and other test utilities.
"""
import pytest
import uuid
from sqlalchemy import create_engine, String
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID

from host_app.app.services.database import Base


class GUID(TypeDecorator):
    """
    Platform-independent GUID type.
    Uses PostgreSQL's UUID type when available, otherwise uses CHAR(36) for SQLite.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(UUID())
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return str(uuid.UUID(value))
            else:
                return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
            else:
                return value


# Monkey patch the UUID columns for testing
def patch_uuid_columns():
    """Temporarily patch UUID columns for SQLite compatibility during testing."""
    from host_app.app.services.database import ChatSession, ChatMessage
    
    # Replace UUID columns with our GUID type for SQLite compatibility
    ChatSession.__table__.columns['id'].type = GUID()
    ChatMessage.__table__.columns['session_id'].type = GUID()


@pytest.fixture(scope="function")
def db_session():
    """
    Create a test database session using SQLite in-memory database.
    This fixture patches UUID columns to be SQLite-compatible.
    """
    # Patch UUID columns for SQLite compatibility
    patch_uuid_columns()
    
    # Create in-memory SQLite database
    engine = create_engine("sqlite:///:memory:", echo=False)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    # Create session
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
