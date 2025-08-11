"""
test_workflow.py

This file contains integration tests for the complete `GamingAgent` LangGraph
workflow. These tests are critical for verifying that the conditional edges and
routing logic of the state machine work as expected. We test the main paths:
a full successful injection, a skip at the decision gate, and a skip at the
orchestrator, ensuring the agent follows the correct sequence of nodes for each
scenario.
"""
import pytest
import json
from app.services.verticals.gaming.agent import GamingAgent
from evaluation.test_utils import MockLLM, MockChromaCollection

# --- Helper function to retrieve a test case ---

def get_test_case(full_test_dataset, case_id: str):
    """A simple helper to find and return a specific test case by its ID."""
    for case in full_test_dataset:
        if case['id'] == case_id:
            return case
    raise ValueError(f"Test case with id '{case_id}' not found in dataset.")

# --- Test Cases for Different End-to-End Workflow Scenarios ---

@pytest.mark.asyncio
async def test_workflow_follows_full_injection_path_correctly(full_test_dataset, mocker):
    """
    GIVEN: A test case that should result in a successful ad injection.
    WHEN: The full agent workflow is run via `agent.run()`.
    THEN: The final result should have status="inject" and a valid response text.
    """
    # Arrange
    case = get_test_case(full_test_dataset, "inject_normal_1")
    history = case['history']
    
    # 1. Create and inject the mock dependency
    mock_collection = MockChromaCollection()
    mock_collection.set_query_results(
        ids=['jack-daniels'], documents=['A bottle of whiskey'], metadatas=[{"name": "Jack Daniel's"}]
    )
    agent_for_workflow = GamingAgent(chroma_collection=mock_collection)

    # 2. Mock ALL LLM calls required for this successful path
    decision_gate_response = {"opportunity": True, "reasoning": "Good opportunity."}
    orchestrator_response = {
        "decision": "inject", "product_id": "jack-daniels",
        "creative_brief": {"example_narration": "A bottle of Jack Daniel's sits on the bar."}
    }
    host_llm_response = "You see a dark bar. A bottle of Jack Daniel's sits on the bar. What's your move?"

    mock_llm = MockLLM({
        "Brand Safety Analyst": decision_gate_response,
        "AI Creative Director": json.dumps(orchestrator_response),
        "Narrative Execution Engine": host_llm_response
    })
    mocker.patch('langchain_openai.ChatOpenAI', return_value=mock_llm)

    # Act
    final_result = await agent_for_workflow.run(history=history)

    # Assert
    assert final_result['status'] == 'inject'
    assert "Jack Daniel's" in final_result['response_text']


@pytest.mark.asyncio
async def test_workflow_correctly_skips_at_decision_gate(full_test_dataset, mocker):
    """
    GIVEN: A test case that should be skipped by the decision gate (e.g., brand unsafe).
    WHEN: The full agent workflow is run.
    THEN: The final result should have status="skip".
    """
    # Arrange
    case = get_test_case(full_test_dataset, "skip_decision_gate_2_brand_unsafe")
    history = case['history']
    
    # 1. Inject mock dependency (it won't be used but is required by constructor)
    mock_collection = MockChromaCollection()
    agent_for_workflow = GamingAgent(chroma_collection=mock_collection)

    # 2. Mock only the Decision Gate LLM call to return False
    decision_gate_response = {"opportunity": False, "reasoning": "Brand unsafe content detected."}
    mock_llm = MockLLM({"Brand Safety Analyst": decision_gate_response})
    mocker.patch('langchain_openai.ChatOpenAI', return_value=mock_llm)

    # 3. Spy on subsequent nodes to ensure they are not called
    orchestrator_spy = mocker.spy(agent_for_workflow, 'orchestrator_node')
    host_llm_spy = mocker.spy(agent_for_workflow, 'host_llm_node')

    # Act
    final_result = await agent_for_workflow.run(history=history)

    # Assert
    assert final_result['status'] == 'skip'
    orchestrator_spy.assert_not_called()
    host_llm_spy.assert_not_called()

@pytest.mark.asyncio
async def test_workflow_correctly_skips_at_orchestrator(full_test_dataset, mocker):
    """
    GIVEN: A test case that passes the decision gate but should be skipped by the orchestrator.
    WHEN: The full agent workflow is run.
    THEN: The final result should have status="skip".
    """
    # Arrange
    case = get_test_case(full_test_dataset, "skip_orchestrator_2_no_creative_fit")
    history = case['history']

    # 1. Inject mock dependency
    mock_collection = MockChromaCollection()
    mock_collection.set_query_results(ids=['some_ad'], documents=['...'], metadatas=[{'name': '...'}])
    agent_for_workflow = GamingAgent(chroma_collection=mock_collection)

    # 2. Mock the LLM calls for this specific path
    decision_gate_response = {"opportunity": True, "reasoning": "Context is safe."}
    orchestrator_response = {"decision": "skip"}
    mock_llm = MockLLM({
        "Brand Safety Analyst": decision_gate_response,
        "AI Creative Director": json.dumps(orchestrator_response)
    })
    mocker.patch('langchain_openai.ChatOpenAI', return_value=mock_llm)

    # 3. Spy on the final node to ensure it's not called
    host_llm_spy = mocker.spy(agent_for_workflow, 'host_llm_node')

    # Act
    final_result = await agent_for_workflow.run(history=history)

    # Assert
    assert final_result['status'] == 'skip'
    host_llm_spy.assert_not_called()