import pytest
from langchain_core.messages import HumanMessage

from react_agent.graph import graph
from react_agent.state import State

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio

async def test_react_flow_for_complex_quote():
    """
    Performs an end-to-end integration test for the ReAct (plan-and-execute) flow.
    """
    print(f"\n--- INTEGRATION TEST: ReAct Flow ---")
    # A more realistic query that includes a budget
    query = "Báo giá cho tôi sơn tường phòng khách 30m2 và lát sàn gỗ phòng ngủ 20m2, ngân sách tổng là 80 triệu"
    print(f"Query: {query}")

    initial_state = State(messages=[HumanMessage(content=query)])

    config = {
        "recursion_limit": 15, # Increased limit for multi-step plans
        "configurable": {
            "model": "qwen3:30b"
        }
    }

    # Use ainvoke to get the final state directly.
    final_state = await graph.ainvoke(initial_state, config=config)

    # Extract the final response for manual evaluation
    final_response_content = ""
    if final_state and final_state.get("final_response"):
        final_response_content = final_state["final_response"]
    
    print(f"\n--- Final Response from Agent (for manual review) ---\n{final_response_content}")

    assert final_response_content, "The agent should have produced a final response."
    # We now expect a more detailed response, not just keywords
    assert "báo giá chi tiết" in final_response_content.lower()
    assert "phù hợp nhất với ngân sách" in final_response_content.lower()
    assert "tổng chi phí" in final_response_content.lower()

    # Check that the plan used the correct high-level tool
    assert "run_detailed_quote" in str(final_state.get("plan", ""))

    print(f"--- ReAct Integration Test COMPLETED ---") 