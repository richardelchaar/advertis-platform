import os
from dotenv import load_dotenv

# This function looks for a .env file and loads its content
# into the environment, making them accessible to os.getenv()
load_dotenv()

# --- OpenAI & LangChain Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "true")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "Advertis_Production")


# --- Service URLs for Docker Network ---
# These are the addresses our service will use to talk to other services
# inside the Docker environment.
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
CHROMA_URL = os.getenv("CHROMA_URL", "http://chroma_db:8000")


# --- Simple Validation ---
# A check to ensure the most critical variable is set before starting.
if not OPENAI_API_KEY:
    raise ValueError("FATAL: OPENAI_API_KEY environment variable is missing.")