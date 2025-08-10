
"""
test_database.py

Unit tests for the database service functions in `host_app/app/services/database.py`.
These tests use an in-memory SQLite database to ensure they are fast and do not
require a running PostgreSQL container. This allows for rapid validation of the
data layer's logic, such as session creation and message history retrieval.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services import database
from app.services.database import User, ChatSession, ChatMessage, Base

# --- Fixture for an in-memory SQLite database session ---

@pytest.fixture(scope="function")
def db_session():
    """
    This fixture sets up an in-memory SQLite database for each test function.
    It creates all the tables, yields a session to the test, and then tears
    down the database after the test is complete. This ensures a clean slate
    for every test.
    """
    # Use in-memory SQLite for fast, isolated tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = TestingSessionLocal()
    try:
        # We also need to patch the global SessionLocal in the database module
        # so that functions like get_or_create_dummy_user use our in-memory DB.
        database.SessionLocal = TestingSessionLocal
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)

# --- Test Cases ---

def test_get_or_create_dummy_user_creation_path(db_session):
    """
    GIVEN: An empty database.
    WHEN: `get_or_create_dummy_user` is called.
    THEN: It should create a new user with id=1 and username='dummy_user',
          commit it to the database, and return the user object.
    """
    # Act
    user = database.get_or_create_dummy_user(db_session)

    # Assert
    assert user is not None
    assert user.id == 1
    assert user.username == "dummy_user"

    # Verify it was actually saved to the DB
    user_from_db = db_session.query(User).filter(User.id == 1).first()
    assert user_from_db is not None
    assert user_from_db.username == "dummy_user"

def test_get_or_create_dummy_user_retrieval_path(db_session):
    """
    GIVEN: A database where the dummy user already exists.
    WHEN: `get_or_create_dummy_user` is called.
    THEN: It should retrieve and return the existing user without creating a new one.
    """
    # Arrange: Create the user first
    existing_user = User(id=1, username="dummy_user")
    db_session.add(existing_user)
    db_session.commit()

    # Act
    user = database.get_or_create_dummy_user(db_session)

    # Assert
    assert user is not None
    assert user.id == 1
    # Ensure no new user was created (still only one user in the table)
    user_count = db_session.query(User).count()
    assert user_count == 1

def test_create_chat_session(db_session):
    """
    GIVEN: A user ID and a system prompt.
    WHEN: `create_chat_session` is called.
    THEN: It should create a new `ChatSession` record AND a corresponding
          initial `ChatMessage` with the role 'system'.
    """
    # Arrange
    user = database.get_or_create_dummy_user(db_session)
    system_prompt = "You are a test assistant."
    app_vertical = "testing"

    # Act
    new_session = database.create_chat_session(db_session, user.id, system_prompt, app_vertical)

    # Assert
    assert new_session is not None
    assert new_session.user_id == user.id
    assert new_session.system_prompt == system_prompt
    assert new_session.app_vertical == app_vertical

    # Verify that the initial system message was also created and linked
    message = db_session.query(ChatMessage).filter(ChatMessage.session_id == new_session.id).first()
    assert message is not None
    assert message.role == "system"
    assert message.content == system_prompt

def test_save_and_get_chat_history(db_session):
    """
    GIVEN: A chat session with several messages.
    WHEN: `save_message` is used to add messages and `get_chat_history` is used to retrieve them.
    THEN: The history should be returned as a list of dictionaries in the correct chronological order.
    """
    # Arrange
    user = database.get_or_create_dummy_user(db_session)
    session = database.create_chat_session(db_session, user.id, "System prompt", "gaming")

    # Act: Save a sequence of messages
    database.save_message(db_session, session.id, "user", "Hello there.")
    database.save_message(db_session, session.id, "assistant", "General Kenobi.")

    # Retrieve the history
    history = database.get_chat_history(db_session, session.id)

    # Assert
    assert len(history) == 3 # system, user, assistant
    
    assert history[0]['role'] == 'system'
    assert history[0]['content'] == 'System prompt'
    
    assert history[1]['role'] == 'user'
    assert history[1]['content'] == 'Hello there.'

    assert history[2]['role'] == 'assistant'
    assert history[2]['content'] == 'General Kenobi.'