# host_app/app/services/advertis_client.py
import httpx
from typing import List, Dict, Optional
from pydantic import BaseModel
from .. import config

# --- Pydantic Models for Deserialization ---
# NOTE: These models duplicate the ones in `advertis_service`. In a larger project,
# these might live in a shared library. For our purposes, duplicating them here
# keeps the services fully decoupled.
class CheckResponse(BaseModel):
    proceed: bool
    reason: str

class AdResponse(BaseModel):
    status: str
    response_text: Optional[str] = None


# --- Asynchronous API Client ---
# We use an async client because our FastAPI/Streamlit apps are async-native.
async def check_opportunity(session_id: str, last_message: str) -> CheckResponse:
    """Makes the fast 'pre-flight' call to the advertis service."""
    url = f"{config.ADVERTIS_API_URL}/v1/check-opportunity"
    payload = {"session_id": session_id, "last_message": last_message}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=5.0)
            response.raise_for_status()  # Raises an exception for 4xx/5xx responses
            return CheckResponse.model_validate(response.json())
        except httpx.HTTPStatusError as e:
            print(f"HTTP error in check_opportunity: {e.response.status_code} - {e.response.text}")
            return CheckResponse(proceed=False, reason="Advertis service error")
        except httpx.RequestError as e:
            print(f"Request error in check_opportunity: {e}")
            return CheckResponse(proceed=False, reason="Advertis service unreachable")


async def get_response(session_id: str, app_vertical: str, history: List[Dict]) -> AdResponse:
    """Makes the main call to get a potentially monetized response."""
    url = f"{config.ADVERTIS_API_URL}/v1/get-response"
    payload = {
        "session_id": session_id,
        "app_vertical": app_vertical,
        "conversation_history": history
    }

    async with httpx.AsyncClient() as client:
        try:
            # This call might take longer, so we give it a longer timeout.
            response = await client.post(url, json=payload, timeout=20.0)
            response.raise_for_status()
            return AdResponse.model_validate(response.json())
        except httpx.HTTPStatusError as e:
            print(f"HTTP error in get_response: {e.response.status_code} - {e.response.text}")
            return AdResponse(status="skip", response_text=None)
        except httpx.RequestError as e:
            print(f"Request error in get_response: {e}")
            return AdResponse(status="skip", response_text=None)