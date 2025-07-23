# advertis_service/app/services/verticals/base_agent.py
from abc import ABC, abstractmethod
from typing import List, Dict

class BaseAgent(ABC):
    """
    This is the abstract base class for all vertical-specific agents.
    It defines the standard interface that the API will use to interact with any agent.
    """
    
    @abstractmethod
    async def run(self, history: List[dict]) -> Dict:
        """
        The main entry point to run the agent.
        Every vertical agent MUST implement this method.
        """
        pass 