"""
test_utils.py

This module contains shared utilities, mocks, and pytest fixtures for the
advertis_service test suite. Centralizing these components keeps test code
clean, reduces duplication, and makes tests easier to maintain. These utilities
are the backbone of our offline testing strategy, allowing us to simulate
external dependencies like Redis, ChromaDB, and the OpenAI API.
"""
import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from typing import Dict, Any, List, Optional
import time

# --- Fixtures for Loading Test Data ---

@pytest.fixture(scope="session")
def full_test_dataset() -> List[Dict[str, Any]]:
    """
    Loads the entire test dataset from the JSON file once per test session.
    This is highly efficient as the file system is accessed only once, and the
    data is cached in memory for all tests in the session.

    Returns:
        A list of dictionaries, where each dictionary is a test case.
    """
    with open("evaluation/data/test_dataset.json", "r") as f:
        return json.load(f)

# --- Mock Classes for Simulating External Dependencies ---

class MockRedisClient:
    """
    A synchronous mock for the Redis client to simulate its behavior without
    requiring a live Redis instance. It uses a simple Python dictionary as an
    in-memory key-value store, making it fast and completely isolated.
    """
    def __init__(self):
        self._store: Dict[str, str] = {}
        print("Initialized MockRedisClient for a test run.")

    def get(self, key: str) -> Optional[str]:
        """Mocks the Redis 'get' method."""
        return self._store.get(key)

    def set(self, key: str, value: str, ex: Optional[int] = None):
        """
        Mocks the Redis 'set' method. The expiration time (`ex`) is ignored
        in this mock, as our tests are short-lived and don't rely on TTL logic.
        """
        self._store[key] = value

    def clear(self):
        """A helper method to reset the store between tests, ensuring no state
        leaks from one test to another."""
        self._store = {}

    def preload_state(self, key: str, state: Optional[Dict[str, Any]]):
        """
        A powerful helper method to pre-populate the mock Redis with a specific
        session state. This is crucial for testing the frequency gate logic under
        various conditions (e.g., ad limit reached, cooldown active).

        It also handles a special case for testing cooldowns by dynamically
        calculating timestamps based on a "now-X" string.
        """
        if state is None:
            if key in self._store:
                del self._store[key]
            return

        # Handle dynamic timestamp for cooldown tests
        if isinstance(state.get("last_ad_timestamp"), str) and "now" in state["last_ad_timestamp"]:
            try:
                # e.g., "now-5" becomes current_time - 5 seconds
                offset = int(state["last_ad_timestamp"].split("-")[1])
                state["last_ad_timestamp"] = int(time.time()) - offset
            except (IndexError, ValueError):
                # Fallback to current time if format is unexpected
                state["last_ad_timestamp"] = int(time.time())

        self.set(key, json.dumps(state))


class MockChromaCollection:
    """
    A mock for the ChromaDB collection object to simulate vector search queries.
    This allows us to test the `orchestrator_node`'s logic for handling retrieved
    documents without needing a live ChromaDB instance or real embeddings.
    """
    def __init__(self):
        # Initialize with an empty result set
        self.mock_results: Dict[str, Any] = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]]
        }

    def set_query_results(self, ids: List[str], documents: List[str], metadatas: List[Dict]):
        """
        Configures the results that the next call to `query` will return.
        This is called by test functions to set up specific retrieval scenarios.
        """
        self.mock_results = {
            "ids": [ids],
            "documents": [documents],
            "metadatas": [metadatas],
            "distances": [[0.1] * len(ids)] # Dummy distances are sufficient for our tests
        }

    def query(self, query_texts: List[str], n_results: int, where: Dict) -> Dict[str, Any]:
        """
        Mocks the actual query method. It simply returns the pre-configured
        results, ignoring the actual query parameters.
        """
        return self.mock_results


class MockLLM:
    """
    A flexible and powerful mock for the LangChain ChatOpenAI model. This is the
    most critical mock in our suite. It allows for deterministic testing of our
    AI agent nodes by returning pre-defined responses based on keywords found
    in the prompt. This lets a single mock instance intelligently serve different
    responses to the Decision Gate, Orchestrator, and Host LLM nodes.
    """
    def __init__(self, response_map: Dict[str, Any]):
        """
        Initializes with a response map.
        The map's keys are keywords to look for in the prompt (e.g., "Brand Safety Analyst").
        The map's values are the exact responses to return for that prompt.
        """
        self.response_map = response_map
        # Mock both async and sync methods to be safe
        self.ainvoke = AsyncMock(side_effect=self._get_response_async)
        self.invoke = MagicMock(side_effect=self._get_response_sync)

    def _get_response_sync(self, messages: Any, *args, **kwargs) -> MagicMock:
        """The core synchronous response logic."""
        prompt_content = self._get_prompt_content(messages)

        for key, response in self.response_map.items():
            if key in prompt_content:
                # For structured outputs, the test may expect a dict.
                # For standard generation, it expects an object with a .content attribute.
                if isinstance(response, dict):
                    # For with_structured_output, the response itself is the model.
                    return response

                # To simulate the structure of a real AIMessage
                mock_response_object = MagicMock()
                mock_response_object.content = response
                return mock_response_object

        # If a prompt is received that isn't in our map, raise an error.
        # This is good practice as it catches unintended LLM calls during tests.
        raise ValueError(f"MockLLM received an unmapped prompt. Content starts with: {prompt_content[:200]}")

    async def _get_response_async(self, messages: Any, *args, **kwargs) -> MagicMock:
        """The async version simply wraps the synchronous logic."""
        return self._get_response_sync(messages, *args, **kwargs)

    def _get_prompt_content(self, messages: Any) -> str:
        """
        Helper method to extract the full text content from various message
        formats that LangChain might pass (string, list of tuples, list of Message objects).
        """
        if isinstance(messages, str):
            return messages
        if isinstance(messages, list):
            full_text = []
            for msg in messages:
                if hasattr(msg, 'content'): # LangChain Message object
                    full_text.append(msg.content)
                elif isinstance(msg, tuple) and len(msg) == 2: # (role, content) tuple
                    full_text.append(str(msg[1]))
            return "\n".join(full_text)
        raise TypeError(f"Unsupported message format for MockLLM: {type(messages)}")

    def with_structured_output(self, *args, **kwargs):
        """
        Mocks the `with_structured_output` chain method. It simply returns
        itself, and our invoke logic will handle returning the pre-configured
        dictionary, which simulates the behavior of the real structured output parser.
        """
        return self
