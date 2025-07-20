import pytest
from langchain_core.messages import HumanMessage

from react_agent.graph import graph
from react_agent.state import State

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio

@pytest.mark.parametrize(
    "query, expected_route",
    [
        ("báo giá chi tiết cho tôi 50m2 gỗ óc chó với ngân sách 80 triệu", "super_tool"),
        ("Tôi có 50 triệu, muốn làm sàn gỗ sồi cho phòng 50m2 thì có được không?", "super_tool"),
        ("Báo giá cho tôi tường phòng khách 30m2 và sàn phòng ngủ 20m2", "plan"),
    ],
)
async def test_integration_flows(query, expected_route):
    """
    Performs end-to-end integration tests for various flows.
    This test runs the full graph and prints the final output for manual review.
    It also checks if the initial routing decision is correct.
    """
    print(f"\n--- INTEGRATION TEST ---")
    print(f"Query: {query}")
    print(f"Expected Route: {expected_route}")

    # 1. Define the initial state with the user's message
    initial_state = State(messages=[HumanMessage(content=query)])

    # 2. Set up the configuration for the graph run
    config = {
        "recursion_limit": 10,
        "configurable": {
            "model": "qwen3:30b"
        }
    }

    # 3. Invoke the graph
    final_state = await graph.ainvoke(initial_state, config=config)

    # 4. Extract and print the final response for manual evaluation
    final_response = final_state.get("final_response", "")
    print(f"\n--- Final Response from Agent (for manual review) ---\n{final_response}")

    # We can also check the intermediate state to see the router's decision
    route_decision = final_state.get("route")
    print(f"Actual Route Taken: {route_decision}")

    # 5. Basic assertion: Ensure the agent produced some output.
    assert final_response, "The agent should have produced a final response."
    assert route_decision == expected_route, f"Agent should have taken the '{expected_route}' route, but took '{route_decision}'."

    print(f"--- Integration Run COMPLETED for query: '{query}' ---") 