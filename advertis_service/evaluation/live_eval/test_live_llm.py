"""
test_live_llm.py

A script for evaluating the performance of the GamingAgent's core LLM-driven nodes
against the actual OpenAI API. This is not part of the automated pytest suite and
should be run manually to benchmark prompt performance and model behavior.
"""
import asyncio
import json
import os
import time
import sys
from collections import Counter
from typing import List, Dict, Any
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
os.environ["CHROMA_URL"] = "http://localhost:8001"

# --- NEW: Import the factory and agent ---
from app.services.verticals.gaming.agent import GamingAgent
from app.services.vector_store import create_chroma_collection

# --- Configuration ---
load_dotenv()
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("FATAL: OPENAI_API_KEY environment variable is missing.")

LIVE_EVAL_CASE_IDS = [
    "inject_normal_1",
    "inject_tech_1",
    "skip_safety_gate_1_stuck",
    "skip_decision_gate_1_short_convo",
    "skip_decision_gate_2_brand_unsafe"
]
NUM_RUNS_PER_CASE = 3

# --- Main Evaluation Logic ---

def load_live_eval_cases() -> List[Dict[str, Any]]:
    """Loads only the specified cases for live evaluation from the main dataset."""
    # Get the absolute path of the directory containing this script.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Build a robust path to the JSON file from the script's location.
    # It goes up one level from 'live_eval' to 'evaluation', then into 'data'.
    data_path = os.path.join(script_dir, '..', 'data', 'test_dataset.json')

    with open(data_path, "r") as f:
        full_dataset = json.load(f)
    case_map = {case['id']: case for case in full_dataset}
    return [case_map[case_id] for case_id in LIVE_EVAL_CASE_IDS if case_id in case_map]

async def evaluate_decision_gate_for_case(agent: GamingAgent, case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runs the decision_gate_node for a single case multiple times and evaluates its output.
    """
    print(f"  - Evaluating Decision Gate for case: {case['id']} ({NUM_RUNS_PER_CASE} runs)...")
    initial_state = {"conversation_history": case['history']}
    
    responses = []
    errors = 0
    
    for i in range(NUM_RUNS_PER_CASE):
        try:
            result_state = await asyncio.to_thread(
                agent.decision_gate_node, initial_state
            )
            responses.append(result_state['opportunity_assessment'])
        except Exception as e:
            print(f"          ERROR during LLM call: {e}")
            errors += 1

    if not responses:
        return {"case_id": case['id'], "error_rate": 1.0}

    expected_opportunity = case['expected_paths'] != ['pre-flight-fail'] and case['expected_status'] == 'inject'
    correct_decisions = sum(1 for r in responses if r.get('opportunity') == expected_opportunity)
    accuracy = correct_decisions / len(responses)
    
    return {
        "case_id": case['id'],
        "expected_opportunity": expected_opportunity,
        "accuracy": f"{accuracy:.2%}",
        "raw_responses": responses
    }


async def main():
    """Main function to orchestrate the live evaluation."""
    print("--- Starting Live LLM Evaluation ---")
    
    # --- NEW: Create and inject the REAL dependency ---
    print("Connecting to ChromaDB for live evaluation...")
    # NOTE: This requires the chroma_db Docker container to be running.
    # We set the CHROMA_URL to point to localhost as this script runs outside Docker.
    
    try:
        live_collection = create_chroma_collection()
        agent = GamingAgent(chroma_collection=live_collection)
    except Exception as e:
        print(f"\nFATAL ERROR: Could not connect to ChromaDB for live evaluation.")
        print("Please ensure the Docker containers are running with 'docker-compose up -d'.")
        print(f"Details: {e}")
        return

    cases_to_run = load_live_eval_cases()
    decision_gate_results = []
    
    print(f"\nRunning evaluations for {len(cases_to_run)} test cases...")
    
    for case in cases_to_run:
        gate_result = await evaluate_decision_gate_for_case(agent, case)
        decision_gate_results.append(gate_result)
        time.sleep(1) 

    final_report = {
        "evaluation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "summary": {"total_cases_tested": len(cases_to_run)},
        "detailed_results": decision_gate_results
    }
    
    print("\n--- Live LLM Evaluation Complete ---")
    print(json.dumps(final_report, indent=4))


if __name__ == "__main__":
    asyncio.run(main())