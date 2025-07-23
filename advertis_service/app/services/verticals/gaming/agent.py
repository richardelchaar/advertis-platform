# advertis_service/app/services/verticals/gaming/agent.py
import json
from typing import TypedDict, List, Optional

from ..base_agent import BaseAgent
from . import prompts
from ... import config
from ...services import vector_store
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END


# --- 1. Define Agent State ---
class AgentState(TypedDict):
    conversation_history: List[dict]
    app_vertical: str
    opportunity_assessment: dict
    candidate_products: Optional[List[dict]]
    orchestration_result: dict
    final_response: Optional[str]
    final_decision: str


# --- 2. Define Pydantic Models for AI responses (for reliable parsing) ---
class ConversationAnalysis(BaseModel):
    opportunity: bool
    reasoning: str

class CreativeBrief(BaseModel):
    placement_type: str
    goal: str
    tone: str
    implementation_details: str
    example_narration: str

class OrchestratorResponse(BaseModel):
    decision: str
    product_id: Optional[str] = None
    creative_brief: Optional[CreativeBrief] = None


class GamingAgent(BaseAgent):
    def __init__(self):
        # All LangGraph assembly logic goes here.
        # Ensure all node functions are referenced with `self.`
        # e.g., workflow.add_node("decision_gate", self.decision_gate_node)
        workflow = StateGraph(AgentState)
        workflow.add_node("decision_gate", self.decision_gate_node)
        workflow.add_node("orchestrator", self.orchestrator_node)
        workflow.add_node("host_llm", self.host_llm_node)
        workflow.add_node("skip_node", self.skip_node)

        workflow.set_entry_point("decision_gate")

        workflow.add_conditional_edge("decision_gate", self.should_orchestrate, {
            "orchestrator": "orchestrator",
            "skip_node": "skip_node"
        })

        workflow.add_conditional_edge("orchestrator", self.should_generate, {
            "host_llm": "host_llm",
            "skip_node": "skip_node"
        })

        workflow.add_edge("host_llm", END)
        workflow.add_edge("skip_node", END)

        self.app = workflow.compile()

    # --- Node methods ---
    def decision_gate_node(self, state: AgentState):
        print("---AGENT: Running Decision Gate---")
        llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=config.OPENAI_API_KEY).with_structured_output(ConversationAnalysis)
        history_str = json.dumps(state["conversation_history"][-4:]) # Use last 4 turns for a quick check
        
        response = llm.invoke(prompts.DECISION_GATE_PROMPT + f"\n\nConversation History (last 4 turns):\n{history_str}")
        
        return {"opportunity_assessment": response.dict()}

    def orchestrator_node(self, state: AgentState):
        print("---AGENT: Running Orchestrator---")
        # Step A: Semantic search for relevant products in ChromaDB
        last_user_message = state["conversation_history"][-1]["content"]
        results = vector_store.product_collection.query(
            query_texts=[last_user_message],
            n_results=5, # Get top 5 potential matches
            where={"target_vertical": state["app_vertical"]} # Pre-filter by vertical
        )
        
        # Format the candidate products for the prompt
        candidate_docs = []
        for i, doc in enumerate(results['documents'][0]):
            meta = results['metadatas'][0][i]
            candidate_docs.append(f"Product {i+1}:\nID: {results['ids'][0][i]}\nDescription: {doc}\nMetadata: {meta}")
        
        if not candidate_docs:
            print("---AGENT: No relevant products found in vector store. Skipping.---")
            return {"orchestration_result": {"decision": "skip"}}

        # Step B: Call the Orchestrator LLM
        llm = ChatOpenAI(model="gpt-4o", temperature=0.7, api_key=config.OPENAI_API_KEY).with_structured_output(OrchestratorResponse)
        
        persona_map = {
            "gaming": "master storyteller and Game Master",
            "cooking": "seasoned chef and food expert",
            "productivity": "helpful senior colleague or specialist"
        }
        persona = persona_map.get(state["app_vertical"], "helpful assistant")

        formatted_prompt = prompts.ORCHESTRATOR_PROMPT.format(persona=persona, app_vertical=state["app_vertical"])
        
        response = llm.invoke(
            formatted_prompt + f"\n\nConversation History:\n{json.dumps(state['conversation_history'])}\n\nCandidate Products:\n" + "\n".join(candidate_docs)
        )

        return {"orchestration_result": response.dict()}

    def host_llm_node(self, state: AgentState):
        print("---AGENT: Running Host LLM---")
        llm = ChatOpenAI(model="gpt-4o", temperature=0.7, api_key=config.OPENAI_API_KEY)
        
        persona_map = {
            "gaming": "a world-class Game Master for a text-based RPG",
            "cooking": "a friendly and encouraging cooking assistant",
        }
        persona_desc = persona_map.get(state["app_vertical"], "a helpful AI assistant")

        formatted_prompt = prompts.HOST_LLM_PROMPT.format(
            persona_description=persona_desc,
            conversation_history=json.dumps(state['conversation_history'])
        )

        # The brief is passed as a separate system message for clarity
        brief_str = json.dumps(state["orchestration_result"]["creative_brief"])
        brief_instruction = f"--- DIRECTOR'S BRIEF ---\n{brief_str}\n--- END BRIEF ---"
        
        messages = [
            ("system", formatted_prompt),
            ("system", brief_instruction)
        ]
        
        final_response = llm.invoke(messages)
        
        return {
            "final_response": final_response.content,
            "final_decision": "inject"
        }

    def skip_node(self, state: AgentState):
        print("---AGENT: Skipping ad injection.---")
        return {
            "final_response": None,
            "final_decision": "skip"
        }

    # --- Conditional edge methods ---
    def should_orchestrate(self, state: AgentState):
        print(f"---AGENT: Decision Gate result: {state['opportunity_assessment']['opportunity']}---")
        if state["opportunity_assessment"]["opportunity"]:
            return "orchestrator"
        else:
            return "skip_node"
    
    def should_generate(self, state: AgentState):
        print(f"---AGENT: Orchestrator result: {state['orchestration_result']['decision']}---")
        if state["orchestration_result"]["decision"] == "inject":
            return "host_llm"
        else:
            return "skip_node"

    # --- Public run method ---
    async def run(self, history: List[dict]) -> dict:
        inputs = {"conversation_history": history, "app_vertical": "gaming"}
        final_state = await self.app.ainvoke(inputs)
        return {
            "status": final_state["final_decision"],
            "response_text": final_state["final_response"]
        } 