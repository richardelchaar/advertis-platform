"""
test_live_llm.py

A script for evaluating the performance of the GamingAgent's core LLM-driven nodes
against the actual OpenAI API. This is not part of the automated pytest suite and
should be run manually to benchmark prompt performance and model behavior.

This script is essential for validating the effectiveness of our prompt engineering.

Usage:
1. Make sure your OPENAI_API_KEY is set in your .env file or as an environment variable.
2. Run from the `advertis_service` directory:
   python evaluation/live_eval/test_live_llm.py

The script will output a JSON report to the console with the evaluation results.
"""
import asyncio
import json
import os
import time
import sys
from collections import Counter
from typing import List, Dict, Any
from dotenv import load_dotenv

# Add the project root to the Python path to allow imports from the `app` module.
# This makes the script runnable from its directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.services.verticals.gaming.agent import GamingAgent

# --- Configuration ---
load_dotenv()
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("FATAL: OPENAI_API_KEY environment variable is missing. This script requires a live API key.")

# We use a smaller, curated subset of the main test dataset for live evaluation
# to manage cost and execution time. These cases are chosen to represent a
# variety of scenarios (inject, skip-by-safety, skip-by-decision).
LIVE_EVAL_CASE_IDS = [
    "inject_normal_1",
    "inject_tech_1",
    "skip_safety_gate_1_stuck", # Note: This will be tested against the decision gate, not the pre-flight
    "skip_decision_gate_1_short_convo",
    "skip_decision_gate_2_brand_unsafe",
    "inject_fantasy_1",
    "skip_orchestrator_1_no_relevant_ads",
    "inject_post_apocalyptic_1",
    "inject_action_type_1"
]
NUM_RUNS_PER_CASE = 3 # Run each case multiple times to check for consistency/variability.

# --- Main Evaluation Logic ---

def load_live_eval_cases() -> List[Dict[str, Any]]:
    """Loads only the specified cases for live evaluation from the main dataset."""
    with open("evaluation/data/test_dataset.json", "r") as f:
        full_dataset = json.load(f)

    # Create a map for quick lookups
    case_map = {case['id']: case for case in full_dataset}
    
    # Return cases in the specified order
    return [case_map[case_id] for case_id in LIVE_EVAL_CASE_IDS if case_id in case_map]

async def evaluate_decision_gate_for_case(agent: GamingAgent, case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runs the decision_gate_node for a single case multiple times and evaluates its output.
    """
    print(f"  - Evaluating Decision Gate for case: {case['id']} ({NUM_RUNS_PER_CASE} runs)...")
    initial_state = {"conversation_history": case['history']}
    
    latencies = []
    responses = []
    errors = 0
    
    for i in range(NUM_RUNS_PER_CASE):
        print(f"    - Run {i+1}/{NUM_RUNS_PER_CASE}...")
        start_time = time.time()
        try:
            # We invoke the node directly with the real LLM
            result_state = await agent.decision_gate_node.ainvoke(initial_state)
            responses.append(result_state['opportunity_assessment'])
        except Exception as e:
            print(f"          ERROR during LLM call: {e}")
            errors += 1
        finally:
            latencies.append(time.time() - start_time)

    # --- Metrics Calculation ---
    if not responses:
        return {"case_id": case['id'], "error_rate": 1.0}

    # Accuracy: How often did the model's decision match the expected status?
    # Note: for pre-flight fail cases, the expected status is 'skip', which means opportunity should be false.
    expected_opportunity = case['expected_paths'] != ['pre-flight-fail'] and case['expected_status'] == 'inject'
    correct_decisions = sum(1 for r in responses if r.get('opportunity') == expected_opportunity)
    accuracy = correct_decisions / len(responses)
    
    # Consistency: What percentage of the time did the model give the most common answer?
    if responses:
        most_common_decision = Counter(r.get('opportunity') for r in responses).most_common(1)[0][1]
        consistency = most_common_decision / len(responses)
    else:
        consistency = 0.0

    return {
        "case_id": case['id'],
        "expected_opportunity": expected_opportunity,
        "accuracy": f"{accuracy:.2%}",
        "consistency": f"{consistency:.2%}",
        "avg_latency_ms": f"{sum(latencies) / len(latencies) * 1000:.2f}",
        "error_rate": f"{errors / NUM_RUNS_PER_CASE:.2%}",
        "raw_responses": responses
    }


async def main():
    """Main function to orchestrate the live evaluation."""
    print("--- Starting Live LLM Evaluation ---")
    print(f"API Key Found: {bool(os.getenv('OPENAI_API_KEY'))}")
    
    cases_to_run = load_live_eval_cases()
    agent = GamingAgent()
    
    decision_gate_results = []
    
    print(f"\nRunning evaluations for {len(cases_to_run)} test cases...")
    
    for case in cases_to_run:
        gate_result = await evaluate_decision_gate_for_case(agent, case)
        decision_gate_results.append(gate_result)
        time.sleep(1) # Small delay to avoid hitting rate limits

    # --- Generate Final Report ---
    overall_accuracy = [float(r['accuracy'].strip('%')) for r in decision_gate_results]
    avg_accuracy = sum(overall_accuracy) / len(overall_accuracy) if overall_accuracy else 0

    final_report = {
        "evaluation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "model_under_test": "gpt-4o",
        "node_under_test": "decision_gate_node",
        "summary": {
            "total_cases_tested": len(cases_to_run),
            "runs_per_case": NUM_RUNS_PER_CASE,
            "average_accuracy": f"{avg_accuracy:.2f}%"
        },
        "detailed_results": decision_gate_results
    }
    
    print("\n--- Live LLM Evaluation Complete ---")
    print("\nFinal Report:")
    print(json.dumps(final_report, indent=4))


if __name__ == "__main__":
    asyncio.run(main())