# host_app/app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# URL for the host app's own database
DATABASE_URL = os.getenv("DATABASE_URL")

# URL to connect to our other microservice
ADVERTIS_API_URL = os.getenv("ADVERTIS_API_URL", "http://advertis_service:8000")

if not DATABASE_URL:
    raise ValueError("FATAL: DATABASE_URL environment variable is missing.")