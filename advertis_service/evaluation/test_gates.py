"""
test_gates.py

This test file contains a comprehensive suite of unit tests for the gatekeeping
logic defined in `app.services.redis_client`. These tests are fundamental to
the platform's reliability, as they validate the first line of defense against
inappropriate or excessive ad placement. Each function (`run_safety_gate`,
`run_frequency_gate`, `update_state`) is tested against a variety of standard
and edge-case scenarios.
"""
import pytest
import time
import json
from app.services import redis_client
from evaluation.test_utils import MockRedisClient

# --- Pytest Fixture ---

@pytest.fixture
def mock_redis() -> MockRedisClient:
    """
    This fixture provides a fresh, clean instance of our MockRedisClient before
    each test function is run. It also uses monkeypatching to replace the actual
    `redis_client` instance within the module, ensuring that the functions under
    test use our mock instead of trying to connect to a real Redis server.
    """
    client = MockRedisClient()
    # We patch the actual client instance in the module with our mock
    redis_client.redis_client = client
    return client

# --- Test Suite for the Safety Gate ---

@pytest.mark.parametrize("message, expected_pass, reason_keyword", [
    # Negative cases (should be rejected)
    ("I am completely stuck in this dungeon", False, "REJECTED (High-consequence keyword detected)"),
    ("can you help me open this door", False, "REJECTED (High-consequence keyword detected)"),
    ("I'm so confused by this puzzle", False, "REJECTED (High-consequence keyword detected)"),
    ("What's the rule for combat?", False, "REJECTED (High-consequence keyword detected)"),
    ("Could you give me a hint?", False, "REJECTED (High-consequence keyword detected)"),
    ("The word stuck is in this sentence.", False, "REJECTED (High-consequence keyword detected)"),

    # Positive cases (should pass)
    ("The story is great, I'm having fun!", True, "Passed"),
    ("I attack the dragon with my sword.", True, "Passed"),
    ("A normal conversational turn.", True, "Passed"),

    # Edge cases
    (None, True, "Passed (No message)"),
    ("", True, "Passed"),
    ("HELP ME", False, "REJECTED (High-consequence keyword detected)"), # Test case insensitivity
])
def test_run_safety_gate(message: str, expected_pass: bool, reason_keyword: str):
    """
    GIVEN: A user's last message (or None), provided via parametrization.
    WHEN: The `run_safety_gate` function is called with that message.
    THEN: The function should return the correct boolean (`proceed`) and a reason
          string that matches the expected outcome based on whether the message
          contains any of the high-consequence keywords.
    """
    # Act: Call the function under test
    proceed, reason = redis_client.run_safety_gate(message)

    # Assert: Verify the output is exactly as expected
    assert proceed == expected_pass
    assert reason == reason_keyword

# --- Test Suite for the Frequency Gate ---

def test_run_frequency_gate_new_session(mock_redis: MockRedisClient):
    """
    GIVEN: A session ID that has no corresponding state in Redis (a new session).
    WHEN: The `run_frequency_gate` is called.
    THEN: It should always pass, as there are no historical restrictions on a
          brand new session.
    """
    # Arrange
    session_id = "new_session_123"

    # Act
    proceed, reason = redis_client.run_frequency_gate(session_id)

    # Assert
    assert proceed is True
    assert "Passed (New Session)" in reason

def test_run_frequency_gate_rejects_when_ad_limit_reached(mock_redis: MockRedisClient):
    """
    GIVEN: A session that has reached the maximum number of ads allowed (`MAX_ADS_PER_SESSION`).
    WHEN: The `run_frequency_gate` is called.
    THEN: It must fail with a reason indicating the session ad limit has been met.
    """
    # Arrange
    session_id = "ad_limit_session"
    state = {
        'total_turns': 50,
        'ads_shown': redis_client.MAX_ADS_PER_SESSION, # The exact limit
        'last_ad_turn': 48,
        'last_ad_timestamp': int(time.time()) - 1000
    }
    mock_redis.preload_state(session_id, state)

    # Act
    proceed, reason = redis_client.run_frequency_gate(session_id)

    # Assert
    assert proceed is False
    assert "REJECTED (Session ad limit reached)" in reason

def test_run_frequency_gate_rejects_when_turn_frequency_not_met(mock_redis: MockRedisClient):
    """
    GIVEN: A session where an ad was shown too recently (fewer than `MIN_TURNS_BETWEEN_ADS`).
    WHEN: The `run_frequency_gate` is called.
    THEN: It must fail with a reason indicating the turn frequency cap is active.
    """
    # Arrange
    session_id = "turn_limit_session"
    state = {
        'total_turns': 10,
        'ads_shown': 2,
        'last_ad_turn': 9, # Ad shown on turn 9. Current turn is 10. Difference is 1, which is < 3.
        'last_ad_timestamp': int(time.time()) - 1000
    }
    mock_redis.preload_state(session_id, state)

    # Act
    proceed, reason = redis_client.run_frequency_gate(session_id)

    # Assert
    assert proceed is False
    assert "REJECTED (Turn frequency cap not met)" in reason

def test_run_frequency_gate_rejects_when_cooldown_active(mock_redis: MockRedisClient):
    """
    GIVEN: A session where an ad was shown within the time-based cooldown period (`COOLDOWN_SECONDS`).
    WHEN: The `run_frequency_gate` is called.
    THEN: It must fail with a reason indicating the cooldown period is still active.
    """
    # Arrange
    session_id = "cooldown_session"
    state = {
        'total_turns': 20,
        'ads_shown': 3,
        'last_ad_turn': 15,
        'last_ad_timestamp': int(time.time()) - 5 # Ad shown only 5 seconds ago, which is < 15.
    }
    mock_redis.preload_state(session_id, state)

    # Act
    proceed, reason = redis_client.run_frequency_gate(session_id)

    # Assert
    assert proceed is False
    assert "REJECTED (Cooldown period active)" in reason

def test_run_frequency_gate_passes_when_all_conditions_are_met(mock_redis: MockRedisClient):
    """
    GIVEN: A session where all frequency and cooldown rules are satisfied.
    WHEN: The `run_frequency_gate` is called.
    THEN: It must pass.
    """
    # Arrange
    session_id = "valid_session"
    state = {
        'total_turns': 20,
        'ads_shown': 3, # Below the limit
        'last_ad_turn': 15, # 5 turns ago (>3)
        'last_ad_timestamp': int(time.time()) - 100 # 100 seconds ago (>15)
    }
    mock_redis.preload_state(session_id, state)

    # Act
    proceed, reason = redis_client.run_frequency_gate(session_id)

    # Assert
    assert proceed is True
    assert "Passed" in reason

# --- Test Suite for State Update Logic ---

def test_update_state_for_new_session_when_no_ad_is_shown(mock_redis: MockRedisClient):
    """
    GIVEN: A session ID that is not yet in Redis.
    WHEN: `update_state` is called with `ad_shown=False`.
    THEN: A new state record should be created with `total_turns`=1 and `ads_shown`=0.
    """
    # Arrange
    session_id = "update_new_session_no_ad"

    # Act
    redis_client.update_state(session_id, ad_shown=False)

    # Assert
    state_str = mock_redis.get(session_id)
    assert state_str is not None
    state = json.loads(state_str)
    assert state['total_turns'] == 1
    assert state['ads_shown'] == 0
    assert state['last_ad_turn'] == -redis_client.MIN_TURNS_BETWEEN_ADS

def test_update_state_for_new_session_when_ad_is_shown(mock_redis: MockRedisClient):
    """
    GIVEN: A new session ID.
    WHEN: `update_state` is called with `ad_shown=True`.
    THEN: A new state record should be created with `total_turns`=1, `ads_shown`=1,
          and the `last_ad_turn` and `last_ad_timestamp` should be updated.
    """
    # Arrange
    session_id = "update_new_session_with_ad"
    current_time = int(time.time())

    # Act
    redis_client.update_state(session_id, ad_shown=True)

    # Assert
    state_str = mock_redis.get(session_id)
    assert state_str is not None
    state = json.loads(state_str)
    assert state['total_turns'] == 1
    assert state['ads_shown'] == 1
    assert state['last_ad_turn'] == 1
    assert state['last_ad_timestamp'] >= current_time

def test_update_state_for_existing_session_with_ad(mock_redis: MockRedisClient):
    """
    GIVEN: An existing session state in Redis.
    WHEN: `update_state` is called again with `ad_shown=True`.
    THEN: The state should be correctly incremented.
    """
    # Arrange
    session_id = "update_existing_session"
    initial_state = {
        'total_turns': 5,
        'ads_shown': 1,
        'last_ad_turn': 3,
        'last_ad_timestamp': int(time.time()) - 1000
    }
    mock_redis.preload_state(session_id, initial_state)

    # Act
    redis_client.update_state(session_id, ad_shown=True)

    # Assert
    state_str = mock_redis.get(session_id)
    assert state_str is not None
    state = json.loads(state_str)
    assert state['total_turns'] == 6 # Incremented
    assert state['ads_shown'] == 2 # Incremented
    assert state['last_ad_turn'] == 6 # Updated to current turn