import pytest
from typing import Dict, Any
import copy

from langchain_core.messages import HumanMessage

from react_agent.state import State
from react_agent.graph import central_router_node, super_tool_executor_node, response_generator_node

pytestmark = pytest.mark.asyncio

async def test_super_tool_flow_flexible_comparison():
    """
    Tests the full "super_tool" flow for a flexible market comparison request
    involving multiple items.
    """
    # 1. Setup: User requests comparison for two different materials
    initial_state = State(
        messages=[HumanMessage(content="So sánh giá thị trường và công ty cho gỗ sồi và đá granite")]
    )

    # 2. Step 1: Central Router Execution
    router_result = await central_router_node(initial_state)
    
    # --- Assertions for Router ---
    assert router_result.get("route") == "super_tool"
    assert router_result.get("tool_name") == "run_market_comparison"
    
    tool_args = router_result.get("tool_args", {})
    assert "items" in tool_args
    assert isinstance(tool_args["items"], list)
    assert len(tool_args["items"]) == 2
    
    # Check if both items are correctly identified (order might vary)
    item_contents = [f"{item.get('material_type')}-{item.get('type')}" for item in tool_args["items"]]
    assert "gỗ-sồi" in item_contents or "wood-oak" in item_contents
    assert "đá-granite" in item_contents or "stone-granite" in item_contents
    
    print("\n--- Router OK ---")
    print(f"Decision: {router_result}")


    # 3. Step 2: Super-Tool Executor Execution
    state_after_router = copy.deepcopy(initial_state)
    state_after_router.route = router_result["route"]
    state_after_router.tool_name = router_result["tool_name"]
    state_after_router.tool_args = tool_args

    executor_result = await super_tool_executor_node(state_after_router)

    # --- Assertions for Executor ---
    assert "past_steps" in executor_result
    step_name, result_str = executor_result["past_steps"][0]
    assert step_name == "run_market_comparison"
    # Check for results of both items
    assert "Comparison for 'sồi'" in result_str or "Comparison for 'oak'" in result_str
    assert "Comparison for 'granite'" in result_str
    assert "Company Price:" in result_str
    assert "Market Price:" in result_str

    print("\n--- Super-Tool Executor OK ---")
    print(f"Result: {result_str}")


    # 4. Step 3: Response Generator Execution
    state_after_executor = copy.deepcopy(state_after_router)
    state_after_executor.past_steps = executor_result["past_steps"]

    final_result = await response_generator_node(state_after_executor)

    # --- Assertions for Response Generator ---
    assert "final_response" in final_result
    final_response = final_result["final_response"]
    assert isinstance(final_response, str)
    assert len(final_response) > 0
    # Check if the final response contains keywords for both items
    assert "sồi" in final_response.lower() or "oak" in final_response.lower()
    assert "granite" in final_response.lower()

    print("\n--- Response Generator OK ---")
    print(f"Final Response: {final_response}") 