# advertis_service/app/services/agent_registry.py
from app.services.verticals.gaming.agent import GamingAgent
# from .verticals.cooking.agent import CookingAgent # Example for the future

# Create a singleton instance of each agent
gaming_agent = GamingAgent()
# cooking_agent = CookingAgent()

# The central registry dictionary
agent_registry = {
    "gaming": gaming_agent,
    # "cooking": cooking_agent,
}

def get_agent(vertical: str):
    """Retrieves a configured agent instance from the registry."""
    return agent_registry.get(vertical.lower()) 