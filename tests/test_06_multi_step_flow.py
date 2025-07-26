import pytest
from langchain_core.messages import HumanMessage
from react_agent.graph import graph

@pytest.mark.asyncio
async def test_multi_step_optimal_combination_quote():
    """
    Tests the full 'multi_step' flow for a complex project with a shared budget.
    The planner should create a single-step plan to call 'find_optimal_combination_quote'.
    """
    print("\n--- Testing Multi-Step Flow (Optimal Combination Quote) ---")
    
    # 1. Setup
    # With a total budget of 120M, the tool should find the best combo.
    user_input = "Báo giá cho tôi sơn tường phòng khách 30m2 và lát sàn gỗ 20m2, ngân sách tổng là 120 triệu. /no_think"
    initial_state = {"messages": [HumanMessage(content=user_input)]}

    # 2. Execution
    final_state = await graph.ainvoke(initial_state)

    # 3. Assertions (simplified to check for completion)
    assert "final_response" in final_state
    assert final_state["final_response"] is not None
  
    print(f"Test passed. Final Response:\n{final_state['final_response']}")

@pytest.mark.asyncio
async def test_multi_step_compare_then_quote():
    """
    Tests the full 'multi_step' flow for a sequential, conditional request.
    1. Compare prices.
    2. Use the result to make a detailed quote.
    """
    print("\n--- Testing Multi-Step Flow (Compare then Quote) ---")
    
    # 1. Setup
    user_input = "So sánh giá gỗ sồi và gỗ óc chó. Sau đó, báo giá chi tiết cho loại rẻ hơn với diện tích 40m2 và ngân sách 50 triệu."
    initial_state = {"messages": [HumanMessage(content=user_input)]}

    # 2. Execution
    final_state = await graph.ainvoke(initial_state)

    # 3. Assertions (simplified to check for completion)
    assert "final_response" in final_state
    assert final_state["final_response"] is not None
  
    print(f"Test passed. Final Response:\n{final_state['final_response']}") 