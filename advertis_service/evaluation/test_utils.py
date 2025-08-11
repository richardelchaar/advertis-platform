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
# The full_test_dataset fixture now lives in evaluation/conftest.py for sharing across tests.

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
    in the prompt.
    """
    def __init__(self, response_map: Dict[str, Any]):
        self.response_map = response_map
        self.ainvoke = AsyncMock(side_effect=self._get_response)
        self.invoke = MagicMock(side_effect=self._get_response)

    def _get_response(self, messages: Any, *args, **kwargs) -> Any:
        """The core response logic for both sync and async calls."""
        prompt_content = self._get_prompt_content(messages)

        for key, response in self.response_map.items():
            if key in prompt_content:
                # If the mapped response is NOT a string (e.g., a Pydantic object),
                # return it directly. This correctly simulates the behavior of
                # a chain that has already parsed the output.
                if not isinstance(response, str):
                    return response

                # Otherwise, for regular string generation, wrap in a mock message object.
                mock_response_object = MagicMock()
                mock_response_object.content = response
                return mock_response_object

        raise ValueError(f"MockLLM received an unmapped prompt. Content starts with: {prompt_content[:200]}")

    def _get_prompt_content(self, messages: Any) -> str:
        """Helper to extract text content from various message formats."""
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
        """Mocks the `with_structured_output` chain method by returning itself."""
        return self
