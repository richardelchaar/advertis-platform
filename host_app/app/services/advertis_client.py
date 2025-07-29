# host_app/app/services/advertis_client.py
import httpx
from typing import List, Dict, Optional, Callable, Awaitable
from pydantic import BaseModel
from app import config

# --- Pydantic Models for Deserialization ---
class CheckResponse(BaseModel):
    proceed: bool
    reason: str

class AdResponse(BaseModel):
    status: str
    response_text: Optional[str] = None

# --- Low-Level API Functions ---
async def _check_opportunity(session_id: str, last_message: str) -> CheckResponse:
    """Makes the fast 'pre-flight' call to the advertis service."""
    url = f"{config.ADVERTIS_API_URL}/v1/check-opportunity"
    payload = {"session_id": session_id, "last_message": last_message}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=5.0)
            response.raise_for_status()
            return CheckResponse.model_validate(response.json())
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"SDK LOG: Error in check_opportunity: {e}")
            return CheckResponse(proceed=False, reason="Advertis service error")

async def _get_response(session_id: str, app_vertical: str, history: List[Dict]) -> AdResponse:
    """Makes the main call to get a potentially monetized response."""
    url = f"{config.ADVERTIS_API_URL}/v1/get-response"
    payload = {
        "session_id": session_id,
        "app_vertical": app_vertical,
        "conversation_history": history
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=20.0)
            response.raise_for_status()
            return AdResponse.model_validate(response.json())
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"SDK LOG: Error in get_response: {e}")
            return AdResponse(status="skip", response_text=None)

# --- HIGH-LEVEL SDK WRAPPER FUNCTION (FOR CUSTOMERS) ---
async def get_monetized_response(
    session_id: str,
    app_vertical: str,
    history: List[Dict],
    fallback_func: Callable[[List[Dict]], Awaitable[str]]
) -> str:
    """
    The main SDK function. It orchestrates the hybrid model logic.
    """
    last_message = history[-1]["content"]
    opportunity = await _check_opportunity(session_id, last_message)

    if opportunity.proceed:
        ad_response = await _get_response(session_id, app_vertical, history)
        if ad_response.status == "inject":
            print("SDK LOG: Injecting response from Advertis.")
            return ad_response.response_text
        else:
            print("SDK LOG: Advertis skipped. Using fallback.")
            return await fallback_func(history)
    else:
        print(f"SDK LOG: Pre-flight check failed ({opportunity.reason}). Using fallback.")
        return await fallback_func(history)