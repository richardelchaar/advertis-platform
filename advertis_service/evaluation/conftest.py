# advertis_service/evaluation/conftest.py
import os
import pytest
import json
from typing import Dict, Any, List

@pytest.fixture(scope="session")
def full_test_dataset() -> List[Dict[str, Any]]:
    """
    Loads the entire test dataset from the JSON file once per test session.
    This fixture is now in conftest.py so it can be shared across all test files.
    """
    # Get the directory of this conftest.py file.
    conf_dir = os.path.dirname(os.path.abspath(__file__))
    # Build a robust path to the data file from this location.
    data_path = os.path.join(conf_dir, 'data', 'test_dataset.json')
    with open(data_path, "r") as f:
        return json.load(f) 