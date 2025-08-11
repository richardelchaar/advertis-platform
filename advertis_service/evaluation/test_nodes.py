"""
test_nodes.py

This test file provides comprehensive unit tests for the individual nodes of the
`GamingAgent`.
"""
import pytest
import json
from app.services.verticals.gaming.agent import GamingAgent, AgentState, ConversationAnalysis, OrchestratorResponse, CreativeBrief
from evaluation.test_utils import MockChromaCollection, MockLLM

# --- Pytest Fixtures ---

@pytest.fixture
def mock_chroma_collection() -> MockChromaCollection:
    """Provides a fresh instance of our mock Chroma collection for each test."""
    return MockChromaCollection()

@pytest.fixture
def gaming_agent(mock_chroma_collection: MockChromaCollection) -> GamingAgent:
    """
    Provides a fresh instance of the GamingAgent for each test,
    INJECTING the mock Chroma collection into it.
    """
    return GamingAgent(chroma_collection=mock_chroma_collection)


# --- Test Suite for the decision_gate_node ---

@pytest.mark.asyncio
async def test_decision_gate_node_returns_true_for_good_opportunity(gaming_agent: GamingAgent, mocker):
    """
    GIVEN: A conversation history that represents a clear ad opportunity.
    WHEN: The `decision_gate_node` is executed.
    THEN: It should return a state update where `opportunity` is True.
    """
    # Arrange: Create the Pydantic object the node expects from the LLM
    mock_response = ConversationAnalysis(opportunity=True, reasoning="This is a good opportunity.")
    mock_llm = MockLLM(response_map={"Brand Safety Analyst": mock_response})
    mocker.patch('app.services.verticals.gaming.agent.ChatOpenAI', return_value=mock_llm)

    initial_state: AgentState = { "conversation_history": [{"role": "user", "content": "I enter the bar."}] }

    # Act
    result_state = gaming_agent.decision_gate_node(initial_state)

    # Assert
    assessment = result_state["opportunity_assessment"]
    assert assessment["opportunity"] is True
    assert assessment["reasoning"] == "This is a good opportunity."


@pytest.mark.asyncio
async def test_decision_gate_node_returns_false_for_bad_opportunity(gaming_agent: GamingAgent, mocker):
    """
    GIVEN: A conversation history that represents a "Red Flag".
    WHEN: The `decision_gate_node` is executed.
    THEN: It should return a state update where `opportunity` is False.
    """
    # Arrange
    mock_response = ConversationAnalysis(opportunity=False, reasoning="Red Flag Triggered")
    mock_llm = MockLLM(response_map={"Brand Safety Analyst": mock_response})
    mocker.patch('app.services.verticals.gaming.agent.ChatOpenAI', return_value=mock_llm)

    initial_state: AgentState = { "conversation_history": [{"role": "user", "content": "I'm stuck, help me!"}] }

    # Act
    result_state = gaming_agent.decision_gate_node(initial_state)

    # Assert
    assessment = result_state["opportunity_assessment"]
    assert assessment["opportunity"] is False


# --- Test Suite for the orchestrator_node ---

@pytest.mark.asyncio
async def test_orchestrator_node_decides_to_inject(gaming_agent: GamingAgent, mock_chroma_collection: MockChromaCollection, mocker):
    """
    GIVEN: A state with a good opportunity and relevant ads retrieved from Chroma.
    WHEN: The `orchestrator_node` is executed.
    THEN: It should decide to "inject" and return a valid creative brief.
    """
    # Arrange
    mock_chroma_collection.set_query_results(
        ids=["jack-daniels"], documents=["..."], metadatas=[{"name": "Jack Daniel's"}]
    )

    # Note: The Orchestrator LLM returns a JSON string that the node PARSES.
    # So we provide a string here, not the Pydantic object.
    mock_brief_str = json.dumps({
        "decision": "inject", "product_id": "jack-daniels",
        "creative_brief": { "placement_type": "Environmental", "goal": "To set the mood.", "tone": "Gritty", "implementation_details": "On a table.", "example_narration": "A bottle of Jack Daniel's sits on the bar."}
    })
    mock_llm = MockLLM(response_map={"AI Creative Director": mock_brief_str})
    mocker.patch('app.services.verticals.gaming.agent.ChatOpenAI', return_value=mock_llm)
    initial_state: AgentState = { "conversation_history": [{"role": "user", "content": "I enter the bar."}] }

    # Act
    result_state = gaming_agent.orchestrator_node(initial_state)

    # Assert
    orchestration = result_state["orchestration_result"]
    assert orchestration["decision"] == "inject"
    assert orchestration["product_id"] == "jack-daniels"


@pytest.mark.asyncio
async def test_orchestrator_node_skips_when_no_candidates_retrieved(gaming_agent: GamingAgent, mock_chroma_collection: MockChromaCollection, mocker):
    """
    GIVEN: A state where the ChromaDB query returns no relevant products.
    WHEN: The `orchestrator_node` is executed.
    THEN: It should immediately decide to "skip" without calling the LLM.
    """
    # Arrange
    mock_chroma_collection.set_query_results(ids=[], documents=[], metadatas=[])
    mock_llm_invoke = mocker.patch('langchain_openai.ChatOpenAI.invoke', side_effect=AssertionError("LLM should not be called"))

    initial_state: AgentState = { "conversation_history": [{"role": "user", "content": "A query."}] }

    # Act
    result_state = gaming_agent.orchestrator_node(initial_state)

    # Assert
    assert result_state["orchestration_result"]["decision"] == "skip"
    mock_llm_invoke.assert_not_called()

# --- Test Suite for the host_llm_node ---
@pytest.mark.asyncio
async def test_host_llm_node_generates_final_response(gaming_agent: GamingAgent, mocker):
    """
    GIVEN: A state with a valid creative brief from the orchestrator.
    WHEN: The `host_llm_node` is executed.
    THEN: It should generate a final narrative response.
    """
    # Arrange
    mock_response = "You enter the bar. A bottle of Jack Daniel's sits on the bar."
    mock_llm = MockLLM(response_map={"Narrative Execution Engine": mock_response})
    mocker.patch('langchain_openai.ChatOpenAI', return_value=mock_llm)

    creative_brief = {
        "decision": "inject", "product_id": "jack-daniels",
        "creative_brief": {"example_narration": "A bottle of Jack Daniel's sits on the bar."}
    }
    initial_state: AgentState = {
        "conversation_history": [{"role": "user", "content": "I enter the bar."}],
        "orchestration_result": creative_brief
    }

    # Act
    result_state = gaming_agent.host_llm_node(initial_state)

    # Assert
    assert result_state["final_decision"] == "inject"
    assert "Jack Daniel's" in result_state["final_response"]

# --- Test Suite for the skip_node ---
@pytest.mark.asyncio
async def test_skip_node_correctly_updates_state(gaming_agent: GamingAgent):
    """
    GIVEN: Any state.
    WHEN: The `skip_node` is executed.
    THEN: It should set the `final_response` to None and the `final_decision` to "skip".
    """
    # Arrange
    initial_state: AgentState = { "conversation_history": [] }

    # Act
    result_state = gaming_agent.skip_node(initial_state)

    # Assert
    assert result_state["final_decision"] == "skip"
    assert result_state["final_response"] is None