# advertis_service/app/services/verticals/gaming/agent.py
import json
from typing import TypedDict, List, Optional

from app import config
from app.services.verticals.base_agent import BaseAgent
from app.services.verticals.gaming import prompts
from chromadb.api.models.Collection import Collection

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
import re


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
    def __init__(self, chroma_collection: Collection):
        # All LangGraph assembly logic goes here.
        workflow = StateGraph(AgentState)
        self.chroma_collection = chroma_collection

        workflow.add_node("decision_gate", self.decision_gate_node)
        workflow.add_node("orchestrator", self.orchestrator_node)
        workflow.add_node("host_llm", self.host_llm_node)
        workflow.add_node("skip_node", self.skip_node)

        workflow.set_entry_point("decision_gate")

        workflow.add_conditional_edges("decision_gate", self.should_orchestrate, {
            "orchestrator": "orchestrator",
            "skip_node": "skip_node"
        })

        workflow.add_conditional_edges("orchestrator", self.should_generate, {
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
        history_str = json.dumps(state["conversation_history"][-4:])

        response = llm.invoke(prompts.DECISION_GATE_PROMPT + f"\n\nConversation History (last 4 turns):\n{history_str}")

        return {"opportunity_assessment": response.model_dump()}

    def orchestrator_node(self, state: AgentState):
        print("---AGENT: Running Orchestrator---")
        last_user_message = state["conversation_history"][-1]["content"]
        results = self.chroma_collection.query(
            query_texts=[last_user_message],
            n_results=5,
            where={"target_vertical": "gaming"}
        )

        candidate_docs = []
        if results['ids'][0]:
            for i, doc in enumerate(results['documents'][0]):
                meta = results['metadatas'][0][i]
                candidate_docs.append(f"Product {i+1}:\nID: {results['ids'][0][i]}\nDescription: {doc}\nMetadata: {json.dumps(meta, indent=2)}")

        print("\n---ORCHESTRATOR DEBUG: Candidate Products---")
        if candidate_docs:
            print("\n".join(candidate_docs))
        else:
            print("No relevant products found in vector store.")
        print("-------------------------------------------\n")

        if not candidate_docs:
            return {"orchestration_result": {"decision": "skip"}}

        llm = ChatOpenAI(model="gpt-4o", temperature=0.7, api_key=config.OPENAI_API_KEY)
        full_prompt = prompts.ORCHESTRATOR_PROMPT + f"\n\nConversation History:\n{json.dumps(state['conversation_history'])}\n\nCandidate Products:\n" + "\n".join(candidate_docs)

        print("\n---ORCHESTRATOR DEBUG: Full Prompt to LLM---")
        print(full_prompt)
        print("--------------------------------------------\n")

        response_str = llm.invoke(full_prompt).content

        try:
            json_match = re.search(r"\{.*\}", response_str, re.DOTALL)
            if not json_match:
                raise json.JSONDecodeError("No JSON object found in the LLM response.", response_str, 0)

            clean_json_str = json_match.group(0)
            response_data = json.loads(clean_json_str)
            validated_response = OrchestratorResponse.model_validate(response_data)
            return {"orchestration_result": validated_response.model_dump()}

        except (json.JSONDecodeError, Exception) as e:
            print(f"---AGENT: ERROR - Failed to parse Orchestrator response. Forcing skip. Error: {e}---")
            print(f"---AGENT: Raw LLM Output was: {response_str}---")
            return {"orchestration_result": {"decision": "skip"}}

    def host_llm_node(self, state: AgentState):
        print("---AGENT: Running Host LLM---")
        llm = ChatOpenAI(model="gpt-4o", temperature=0.7, api_key=config.OPENAI_API_KEY)
        system_prompt = prompts.HOST_LLM_PROMPT
        brief_str = json.dumps(state["orchestration_result"]["creative_brief"])
        brief_instruction = f"--- DIRECTOR'S BRIEF ---\n{brief_str}\n--- END BRIEF ---"

        messages = [
            ("system", system_prompt),
            *state["conversation_history"],
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
        assessment = state['opportunity_assessment']
        print(f"---AGENT: Decision Gate result: {assessment['opportunity']} | Reason: {assessment['reasoning']}---")
        if assessment["opportunity"]:
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
    async def run(self, history: list[dict]) -> dict:
        inputs = {"conversation_history": history, "app_vertical": "gaming"}
        final_state = await self.app.ainvoke(inputs)
        return {
            "status": final_state["final_decision"],
            "response_text": final_state["final_response"]
        } 