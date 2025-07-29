# host_app/app/services/database.py
import uuid
from datetime import datetime
from typing import List, Dict

from sqlalchemy import (create_engine, Column, Integer, String, 
                        DateTime, ForeignKey, Text, CheckConstraint)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

from app import config

# --- Database Setup ---
engine = create_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- ORM Models (Defines our tables) ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    sessions = relationship("ChatSession", back_populates="user")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    system_prompt = Column(Text, nullable=True)
    app_vertical = Column(String, nullable=False)
    
    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"))
    role = Column(String, CheckConstraint("role IN ('user', 'assistant', 'system')"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("ChatSession", back_populates="messages")


# --- Database Initialization ---
def init_db():
    """Creates all database tables if they don't exist."""
    print("DATABASE: Initializing database and creating tables...")
    Base.metadata.create_all(bind=engine)
    print("DATABASE: Tables created successfully.")


def get_or_create_dummy_user(db_session):
    """Finds the dummy user with ID 1, or creates it if it doesn't exist."""
    dummy_user = db_session.query(User).filter(User.id == 1).first()
    if not dummy_user:
        print("DATABASE: Dummy user not found. Creating...")
        dummy_user = User(id=1, username="dummy_user")
        db_session.add(dummy_user)
        db_session.commit()
        db_session.refresh(dummy_user)
        print("DATABASE: Dummy user created.")
    return dummy_user


# --- Helper Functions (What our app will use) ---
def get_db():
    """Dependency to get a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_chat_session(db_session, user_id: int, system_prompt: str, app_vertical: str) -> ChatSession:
    """Creates a new chat session and its initial system message in the database."""
    # Step 1: Create the session object
    new_session = ChatSession(
        user_id=user_id,
        system_prompt=system_prompt,
        app_vertical=app_vertical
    )
    db_session.add(new_session)
    db_session.commit()
    db_session.refresh(new_session) # This populates the new_session.id from the DB

    # Step 2: Now that the session has an ID, create the system message
    system_message = ChatMessage(
        session_id=new_session.id,
        role="system",
        content=system_prompt
    )
    db_session.add(system_message)
    db_session.commit() # Commit the new message

    return new_session

def get_chat_history(db_session, session_id: uuid.UUID) -> List[Dict]:
    """Retrieves the conversation history for a given session."""
    messages = db_session.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    return [{"role": msg.role, "content": msg.content} for msg in messages]

def save_message(db_session, session_id: uuid.UUID, role: str, content: str):
    """Saves a new message to the conversation history."""
    new_message = ChatMessage(session_id=session_id, role=role, content=content)
    db_session.add(new_message)
    db_session.commit()

# On module load, try to initialize the database.
init_db()