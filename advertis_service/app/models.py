from pydantic import BaseModel
from typing import List, Optional

# --- Models for the /v1/check-opportunity endpoint ---

class CheckRequest(BaseModel):
    """The request payload for the pre-flight check."""
    session_id: str
    # The blueprint mentions a simple keyword safety gate, which needs the last message.
    last_message: Optional[str] = None

class CheckResponse(BaseModel):
    """The response from the pre-flight check."""
    proceed: bool
    reason: str


# --- Models for the /v1/get-response endpoint ---

class AdRequest(BaseModel):
    """The request payload for the main response generation call."""
    session_id: str
    app_vertical: str
    conversation_history: List[dict]

class AdResponse(BaseModel):
    """The final response containing the status and generated text."""
    status: str  # Will be "inject" or "skip"
    response_text: Optional[str] = None # Will be null if status is "skip"