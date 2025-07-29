from fastapi import FastAPI, HTTPException
# In advertis_service/app/main.py
from app.models import CheckRequest, CheckResponse, AdRequest, AdResponse
from app.services.agent_registry import get_agent
from app.services import redis_client

# Initialize the FastAPI app
app = FastAPI(
    title="Advertis Inference Service",
    description="Provides narrative-as-a-service with integrated product placement.",
    version="1.0.0"
)

# --- API Endpoints ---

@app.get("/health", summary="Health Check")
async def health_check():
    """A simple endpoint to confirm the service is running."""
    return {"status": "ok"}

@app.post("/v1/check-opportunity", response_model=CheckResponse, summary="Pre-flight Check")
async def check_opportunity_endpoint(request: CheckRequest):
    """
    Runs fast, non-AI checks to see if an ad is even possible.
    This should be called on every conversational turn.
    """
    # 1. Run the simple keyword-based safety gate
    is_safe, reason = redis_client.run_safety_gate(request.last_message)
    if not is_safe:
        return CheckResponse(proceed=False, reason=reason)

    # 2. Run the frequency and cooldown gate against Redis
    proceed, reason = redis_client.run_frequency_gate(request.session_id)
    return CheckResponse(proceed=proceed, reason=reason)

@app.post("/v1/get-response", response_model=AdResponse, summary="Generate Monetized Response")
async def get_response_endpoint(request: AdRequest):
    """
    Runs the full AI agent graph to generate a response.
    This is the expensive call, only made if /check-opportunity succeeds.
    """
    # 1. Get the correct agent from the registry based on the request
    agent = get_agent(request.app_vertical)
    if not agent:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported or invalid 'app_vertical': {request.app_vertical}"
        )

    try:
        # 2. Run the selected agent
        result = await agent.run(history=request.conversation_history)
        
        # 3. Update the frequency state in Redis
        ad_was_shown = (result["status"] == "inject")
        redis_client.update_state(request.session_id, ad_shown=ad_was_shown)

        # 4. Return the final, structured response
        return AdResponse(
            status=result["status"],
            response_text=result["response_text"]
        )

    except Exception as e:
        # Basic error handling
        print(f"An error occurred in get_response_endpoint: {e}")
        # In production, you'd have more robust logging (e.g., to Sentry)
        raise HTTPException(status_code=500, detail="An internal error occurred.")