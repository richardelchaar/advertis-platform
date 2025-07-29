import redis
import json
from datetime import datetime
from app import config

# --- Client Initialization ---
# This creates a single, reusable connection pool to our Redis service.
redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)

# --- Constants from the Business Logic ---
MAX_ADS_PER_SESSION = 15
MIN_TURNS_BETWEEN_ADS = 3
COOLDOWN_SECONDS = 15
HIGH_CONSEQUENCE_KEYWORDS = ["help", "stuck", "hint", "rule", "stuck", "confused"]

# --- Gate Functions ---

def update_state(session_id: str, ad_shown: bool = False):
    """
    Updates the session state in Redis after a turn.
    This will be called by the main endpoint logic later.
    """
    state_str = redis_client.get(session_id)
    # Set a default state for a new session
    state = json.loads(state_str) if state_str else {
        'total_turns': 0, 
        'ads_shown': 0, 
        'last_ad_turn': -MIN_TURNS_BETWEEN_ADS, 
        'last_ad_timestamp': 0
    }

    state['total_turns'] += 1
    if ad_shown:
        state['ads_shown'] += 1
        state['last_ad_timestamp'] = int(datetime.now().timestamp())
        state['last_ad_turn'] = state['total_turns']
    
    # Set an expiration on the key so Redis doesn't fill up with old sessions
    # Expires after 2 hours of inactivity.
    redis_client.set(session_id, json.dumps(state), ex=7200)

def run_frequency_gate(session_id: str) -> tuple[bool, str]:
    """Checks Redis to enforce frequency and cooldown rules."""
    state_str = redis_client.get(session_id)
    if not state_str:
        return True, "Frequency Gate: Passed (New Session)"

    state = json.loads(state_str)
    now = int(datetime.now().timestamp())

    if state.get('ads_shown', 0) >= MAX_ADS_PER_SESSION:
        return False, "Frequency Gate: REJECTED (Session ad limit reached)"

    if (state.get('total_turns', 0) - state.get('last_ad_turn', 0)) < MIN_TURNS_BETWEEN_ADS:
        return False, "Frequency Gate: REJECTED (Turn frequency cap not met)"

    if (now - state.get('last_ad_timestamp', 0)) < COOLDOWN_SECONDS:
        return False, "Frequency Gate: REJECTED (Cooldown period active)"

    return True, "Frequency Gate: Passed"

def run_safety_gate(last_message: str | None) -> tuple[bool, str]:
    """Scans the last message for keywords indicating player frustration."""
    if not last_message:
        return True, "Safety Gate: Passed (No message)"

    if any(keyword in last_message.lower() for keyword in HIGH_CONSEQUENCE_KEYWORDS):
        return False, "Safety Gate: REJECTED (High-consequence keyword detected)"

    return True, "Safety Gate: Passed"