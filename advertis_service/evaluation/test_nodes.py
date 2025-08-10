"""
test_nodes.py

This test file provides comprehensive unit tests for the individual nodes of the
`GamingAgent` found in `app.services.verticals.gaming.agent`. Each node represents
a distinct step in the AI decision-making process. These tests are crucial for
ensuring that each component of the agent's "brain" functions correctly before
we test them together in the workflow integration tests. We use extensive
mocking to isolate each node from its dependencies (LLM, ChromaDB).
"""
import pytest
import json
from app.services.verticals.gaming.agent import GamingAgent, AgentState
from app.services import vector_store
from evaluation.test_utils import MockChromaCollection, MockLLM

# --- Pytest Fixtures ---

@pytest.fixture
def gaming_agent() -> GamingAgent:
    """
    Provides a fresh, clean instance of the GamingAgent for each test function.
    This ensures that there is no state leakage between tests.
    """
    return GamingAgent()

@pytest.fixture
def mock_chroma(mocker) -> MockChromaCollection:
    """
    Fixture to mock the ChromaDB collection used in the orchestrator node.
    It uses mocker to patch the actual `product_collection` instance in the
    `vector_store` module, replacing it with our controllable mock.
    """
    mock_collection = MockChromaCollection()
    mocker.patch('app.services.vector_store.product_collection', mock_collection)
    return mock_collection


# --- Test Suite for the decision_gate_node ---

@pytest.mark.asyncio
async def test_decision_gate_node_returns_true_for_good_opportunity(gaming_agent: GamingAgent, mocker):
    """
    GIVEN: A conversation history that represents a clear and appropriate ad opportunity.
    WHEN: The `decision_gate_node` is executed.
    THEN: It should correctly invoke the LLM and return a state update with
          `opportunity_assessment` dictionary where `opportunity` is True.
    """
    # Arrange:
    # 1. Define the mock LLM's pre-canned response for this scenario.
    #    The `with_structured_output` expects a dict-like object.
    mock_response = {"opportunity": True, "reasoning": "This is a good opportunity."}
    mock_llm = MockLLM(response_map={"Brand Safety Analyst": mock_response})
    mocker.patch('langchain_openai.ChatOpenAI', return_value=mock_llm)

    # 2. Define the initial state for the node.
    initial_state: AgentState = {
        "conversation_history": [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "I enter the bar."}
        ],
        "app_vertical": "gaming",
        "opportunity_assessment": {}, "candidate_products": None,
        "orchestration_result": {}, "final_response": None, "final_decision": ""
    }

    # Act
    result_state = await gaming_agent.decision_gate_node.ainvoke(initial_state)

    # Assert
    assert "opportunity_assessment" in result_state
    assessment = result_state["opportunity_assessment"]
    assert assessment["opportunity"] is True
    assert assessment["reasoning"] == "This is a good opportunity."


@pytest.mark.asyncio
async def test_decision_gate_node_returns_false_for_bad_opportunity(gaming_agent: GamingAgent, mocker):
    """
    GIVEN: A conversation history that represents a "Red Flag" (e.g., user frustration).
    WHEN: The `decision_gate_node` is executed.
    THEN: It should return a state update with `opportunity_assessment` having `opportunity: false`.
    """
    # Arrange
    # 1. Mock the LLM to return a "false" assessment
    mock_response = {"opportunity": False, "reasoning": "Red Flag Triggered: Player is Stuck or Frustrated."}
    mock_llm = MockLLM(response_map={"Brand Safety Analyst": mock_response})
    mocker.patch('langchain_openai.ChatOpenAI', return_value=mock_llm)

    # 2. Define the initial state with a "stuck" message.
    initial_state: AgentState = {
        "conversation_history": [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "I'm stuck, help me!"}
        ],
        "app_vertical": "gaming",
        "opportunity_assessment": {}, "candidate_products": None,
        "orchestration_result": {}, "final_response": None, "final_decision": ""
    }

    # Act
    result_state = await gaming_agent.decision_gate_node.ainvoke(initial_state)

    # Assert
    assert "opportunity_assessment" in result_state
    assessment = result_state["opportunity_assessment"]
    assert assessment["opportunity"] is False
    assert "Red Flag" in assessment["reasoning"]


# --- Test Suite for the orchestrator_node ---

@pytest.mark.asyncio
async def test_orchestrator_node_decides_to_inject(gaming_agent: GamingAgent, mock_chroma: MockChromaCollection, mocker):
    """
    GIVEN: A state with a good opportunity and relevant ads retrieved from Chroma.
    WHEN: The `orchestrator_node` is executed.
    THEN: It should decide to "inject" and return a valid creative brief.
    """
    # Arrange
    # 1. Mock Chroma to return some relevant products
    mock_chroma.set_query_results(
        ids=["coca-cola", "jack-daniels"],
        documents=["A refreshing can of coke.", "A bottle of whiskey."],
        metadatas=[{"name": "Coca-Cola"}, {"name": "Jack Daniel's"}]
    )

    # 2. Mock the Orchestrator LLM to decide "inject"
    mock_brief = {
        "decision": "inject",
        "product_id": "jack-daniels",
        "creative_brief": {
            "placement_type": "Environmental Detail", "goal": "To set the mood.",
            "tone": "Gritty", "implementation_details": "Mention it on a table.",
            "example_narration": "A bottle of Jack Daniel's sits on the dusty bar."
        }
    }
    # Important: The mock LLM returns a JSON string, which the node then parses.
    mock_llm = MockLLM(response_map={"AI Creative Director": json.dumps(mock_brief)})
    mocker.patch('langchain_openai.ChatOpenAI', return_value=mock_llm)

    # 3. Define the initial state
    initial_state: AgentState = {
        "conversation_history": [{"role": "user", "content": "I enter the gritty noir bar."}],
        "app_vertical": "gaming",
        "opportunity_assessment": {"opportunity": True, "reasoning": "Good opportunity"},
        "candidate_products": None, "orchestration_result": {},
        "final_response": None, "final_decision": ""
    }

    # Act
    result_state = await gaming_agent.orchestrator_node.ainvoke(initial_state)

    # Assert
    assert "orchestration_result" in result_state
    orchestration = result_state["orchestration_result"]
    assert orchestration["decision"] == "inject"
    assert orchestration["product_id"] == "jack-daniels"
    assert orchestration["creative_brief"]["example_narration"] is not None


@pytest.mark.asyncio
async def test_orchestrator_node_skips_when_no_candidates_retrieved(gaming_agent: GamingAgent, mock_chroma: MockChromaCollection, mocker):
    """
    GIVEN: A state where the ChromaDB query returns no relevant products.
    WHEN: The `orchestrator_node` is executed.
    THEN: It should immediately decide to "skip" without calling the LLM.
    """
    # Arrange
    # 1. Mock Chroma to return no results
    mock_chroma.set_query_results(ids=[], documents=[], metadatas=[])

    # 2. The LLM should not even be called. We can use a spy to verify this.
    mock_llm_invoke = mocker.patch('langchain_openai.ChatOpenAI.invoke', side_effect=AssertionError("LLM should not be called"))

    # 3. Define initial state
    initial_state: AgentState = {
        "conversation_history": [{"role": "user", "content": "A very abstract query."}],
        "app_vertical": "gaming",
        "opportunity_assessment": {"opportunity": True, "reasoning": "Good opportunity"},
        "candidate_products": None, "orchestration_result": {},
        "final_response": None, "final_decision": ""
    }

    # Act
    result_state = await gaming_agent.orchestrator_node.ainvoke(initial_state)

    # Assert
    assert "orchestration_result" in result_state
    orchestration = result_state["orchestration_result"]
    assert orchestration["decision"] == "skip"
    mock_llm_invoke.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_node_skips_when_llm_decides_to(gaming_agent: GamingAgent, mock_chroma: MockChromaCollection, mocker):
    """
    GIVEN: Relevant ads are retrieved, but the Orchestrator LLM decides none are a good creative fit.
    WHEN: The `orchestrator_node` is executed.
    THEN: It should respect the LLM's decision and return a "skip" status.
    """
    # Arrange
    # 1. Mock Chroma to return some products
    mock_chroma.set_query_results(ids=["coca-cola"], documents=["A can of coke."], metadatas=[{"name": "Coca-Cola"}])

    # 2. Mock the LLM to explicitly return a "skip" decision
    mock_llm = MockLLM(response_map={"AI Creative Director": '{"decision": "skip"}'})
    mocker.patch('langchain_openai.ChatOpenAI', return_value=mock_llm)

    # 3. Define initial state
    initial_state: AgentState = {
        "conversation_history": [{"role": "user", "content": "I cast a magic spell."}],
        "app_vertical": "gaming",
        "opportunity_assessment": {"opportunity": True, "reasoning": "Good opportunity"},
        "candidate_products": None, "orchestration_result": {},
        "final_response": None, "final_decision": ""
    }

    # Act
    result_state = await gaming_agent.orchestrator_node.ainvoke(initial_state)

    # Assert
    assert "orchestration_result" in result_state
    orchestration = result_state["orchestration_result"]
    assert orchestration["decision"] == "skip"


# --- Test Suite for the host_llm_node ---

@pytest.mark.asyncio
async def test_host_llm_node_generates_final_response(gaming_agent: GamingAgent, mocker):
    """
    GIVEN: A state with a valid creative brief from the orchestrator.
    WHEN: The `host_llm_node` is executed.
    THEN: It should generate a final narrative response that incorporates the brief's
          `example_narration` and set the final decision to "inject".
    """
    # Arrange
    # 1. Mock the Host LLM to return a plausible narrative response
    mock_response = "You enter the bar, rain slicking the floor. A bottle of Jack Daniel's sits on the dusty bar, catching the dim light. The bartender eyes you suspiciously. What do you do?"
    mock_llm = MockLLM(response_map={"Narrative Execution Engine": mock_response})
    mocker.patch('langchain_openai.ChatOpenAI', return_value=mock_llm)

    # 2. Define the creative brief that this node receives as input
    creative_brief = {
        "decision": "inject", "product_id": "jack-daniels",
        "creative_brief": {
            "placement_type": "Environmental", "goal": "Set mood", "tone": "Noir",
            "implementation_details": "On bar",
            "example_narration": "A bottle of Jack Daniel's sits on the dusty bar, catching the dim light."
        }
    }
    initial_state: AgentState = {
        "conversation_history": [{"role": "user", "content": "I enter the bar."}],
        "orchestration_result": creative_brief,
        "app_vertical": "gaming", "opportunity_assessment": {}, "candidate_products": None,
        "final_response": None, "final_decision": ""
    }

    # Act
    result_state = await gaming_agent.host_llm_node.ainvoke(initial_state)

    # Assert
    assert result_state["final_decision"] == "inject"
    assert result_state["final_response"] is not None
    # Check that the core of the brief was included in the final response
    assert "bottle of Jack Daniel's" in result_state["final_response"]


# --- Test Suite for the skip_node ---

@pytest.mark.asyncio
async def test_skip_node_correctly_updates_state(gaming_agent: GamingAgent):
    """
    GIVEN: Any state.
    WHEN: The `skip_node` is executed.
    THEN: It should set the `final_response` to None and the `final_decision` to "skip".
    """
    # Arrange
    initial_state: AgentState = {
        "conversation_history": [], "app_vertical": "", "opportunity_assessment": {},
        "candidate_products": None, "orchestration_result": {},
        "final_response": "some previous text that should be cleared", "final_decision": "inject"
    }

    # Act
    result_state = await gaming_agent.skip_node.ainvoke(initial_state)

    # Assert
    assert result_state["final_decision"] == "skip"
    assert result_state["final_response"] is None