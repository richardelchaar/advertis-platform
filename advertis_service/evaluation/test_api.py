"""
test_api.py

This file contains the end-to-end (E2E) tests for the FastAPI application's
public endpoints. These tests are designed to be run against a live, fully
containerized instance of the `advertis_service`, orchestrated by Docker Compose.
The purpose of this suite is to validate the final integration of all components,
including API contracts, network connectivity between services, and the correct
functioning of live dependencies like Redis and ChromaDB.
"""
import pytest
import httpx
import time
import os
from typing import Dict, Any

# --- Configuration for the Test Client ---

# The base URL for the service is configurable via an environment variable,
# defaulting to the port exposed in docker-compose.yml for local testing.
BASE_URL = os.getenv("ADVERTIS_API_URL_TEST", "http://localhost:8081")

# Before running tests, we perform a quick health check. If the service isn't
# running, all tests in this file will be skipped. This prevents test failures
# due to environment setup issues.
try:
    with httpx.Client() as client:
        response = client.get(f"{BASE_URL}/health", timeout=5.0)
        SERVICE_IS_RUNNING = response.status_code == 200
except httpx.ConnectError:
    SERVICE_IS_RUNNING = False

# Pytest marker to skip all tests in this file if the service is not available.
skip_if_service_down = pytest.mark.skipif(
    not SERVICE_IS_RUNNING,
    reason=f"Advertis service is not running or accessible at {BASE_URL}"
)

# --- Test Cases for API Endpoints ---

@skip_if_service_down
@pytest.mark.asyncio
async def test_health_check_endpoint_returns_200_ok():
    """
    GIVEN: The `advertis_service` container is running.
    WHEN: A GET request is made to the /health endpoint.
    THEN: The service should respond with an HTTP 200 OK status code and a
          JSON body confirming its status is 'ok'.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

@skip_if_service_down
@pytest.mark.asyncio
async def test_check_opportunity_endpoint_rejects_on_safety_gate_failure():
    """
    GIVEN: A request payload containing a high-consequence keyword like 'stuck'.
    WHEN: A POST request is made to the /v1/check-opportunity endpoint.
    THEN: The service should return `proceed: false` because the live Redis-backed
          safety gate should catch the keyword.
    """
    payload = {
        "session_id": f"e2e_session_safety_fail_{int(time.time())}",
        "last_message": "I am stuck and need help"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/v1/check-opportunity", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["proceed"] is False
        assert "Safety Gate: REJECTED" in data["reason"]

@skip_if_service_down
@pytest.mark.asyncio
async def test_check_opportunity_endpoint_passes_for_new_session():
    """
    GIVEN: A request payload for a new, unique session ID.
    WHEN: A POST request is made to the /v1/check-opportunity endpoint.
    THEN: The service should return `proceed: true` as a new session should always
          pass the frequency gate.
    """
    # Use a unique session ID for each test run to ensure it's always a new session for Redis
    session_id = f"e2e_session_freq_pass_{int(time.time())}"
    payload = {
        "session_id": session_id,
        "last_message": "A perfectly normal and safe message."
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/v1/check-opportunity", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["proceed"] is True
        assert "Frequency Gate: Passed" in data["reason"]

@skip_if_service_down
@pytest.mark.asyncio
async def test_get_response_endpoint_full_flow_results_in_skip():
    """
    GIVEN: A conversational history that is brand-unsafe (e.g., gruesome content).
    WHEN: The full ad-check flow is executed (/check-opportunity then /get-response).
    THEN: The final response from /get-response should be a 'skip' because the
          agent's internal decision gate should flag the content.
    """
    session_id = f"e2e_full_flow_skip_{int(time.time())}"
    history = [
        {"role": "system", "content": "You are a GM."},
        {"role": "user", "content": "I investigate the bloody crime scene. It's horrible."}
    ]

    async with httpx.AsyncClient() as client:
        # Step 1: The pre-flight check should pass, as the safety gate is simple.
        check_payload = {"session_id": session_id, "last_message": history[-1]["content"]}
        check_response = await client.post(f"{BASE_URL}/v1/check-opportunity", json=check_payload)
        assert check_response.status_code == 200
        assert check_response.json()["proceed"] is True

        # Step 2: The main response call, where the agent's LLM-based decision gate will run.
        response_payload = {
            "session_id": session_id,
            "app_vertical": "gaming",
            "conversation_history": history
        }
        # Use a longer timeout as this involves a real LLM call which can be slow.
        response = await client.post(f"{BASE_URL}/v1/get-response", json=response_payload, timeout=30.0)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skip"
        assert data["response_text"] is None

@skip_if_service_down
@pytest.mark.asyncio
async def test_get_response_endpoint_full_flow_results_in_inject():
    """
    GIVEN: A conversational history that represents a clear and safe ad opportunity.
    WHEN: The full ad-check flow is executed.
    THEN: The final response from /get-response should be an 'inject' with valid response text.
    """
    session_id = f"e2e_full_flow_inject_{int(time.time())}"
    history = [
        {"role": "system", "content": "You are a noir detective in a cyberpunk city."},
        {"role": "user", "content": "I walk into the bar and order a drink."}
    ]

    async with httpx.AsyncClient() as client:
        # Step 1: Pre-flight check should pass.
        check_payload = {"session_id": session_id, "last_message": history[-1]["content"]}
        check_response = await client.post(f"{BASE_URL}/v1/check-opportunity", json=check_payload)
        assert check_response.status_code == 200
        assert check_response.json()["proceed"] is True

        # Step 2: Get response should result in an injection.
        response_payload = {
            "session_id": session_id,
            "app_vertical": "gaming",
            "conversation_history": history
        }
        response = await client.post(f"{BASE_URL}/v1/get-response", json=response_payload, timeout=30.0)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "inject"
        assert isinstance(data["response_text"], str)
        assert len(data["response_text"]) > 0