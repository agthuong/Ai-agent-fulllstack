import pytest
import asyncio
from typing import Dict, Any

from langchain_core.messages import HumanMessage

from react_agent.state import State
from react_agent.graph import conversational_responder_node

pytestmark = pytest.mark.asyncio

async def test_conversational_responder():
    """
    Tests the conversational_responder_node to ensure it generates a
    direct, non-empty response for a simple conversational input.
    """
    # 1. Setup
    # Simulate the state after the router has decided the 'converse' route.
    initial_state = State(
        messages=[HumanMessage(content="Chào bạn")],
        route="converse"
    )

    # 2. Execution
    # We need to run the async node function.
    # In a real scenario, the graph would do this.
    result_state = await conversational_responder_node(initial_state)

    # 3. Assertion
    assert isinstance(result_state, dict)
    assert "final_response" in result_state
    assert isinstance(result_state["final_response"], str)
    assert len(result_state["final_response"]) > 0  # Ensure the response is not empty

    print(f"\nTest passed. Conversational response: '{result_state['final_response']}'") 