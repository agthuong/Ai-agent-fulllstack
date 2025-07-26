import pytest
from langchain_core.messages import HumanMessage

from react_agent.graph import graph

@pytest.mark.asyncio
async def test_full_detailed_quote_flow_success():
    """
    Tests the full 'single_step' flow for a successful detailed quote request.
    Verifies routing, tool execution, and final response generation.
    """
    print("\n--- Testing Full Detailed Quote Flow (Success) ---")
    
    # 1. Setup
    # Budget is 80,000,000 for 50m2, which is 1,600,000/m2.
    # This should be enough for "Gỗ Óc Chó loại 2" (1,500,000) but not "loại 1" (1,800,000)
    # based on the prices in `data_new/gỗ_prices.json`.
    user_input = "Báo giá cho tôi 50m2 gỗ óc chó với ngân sách 80 triệu"
    initial_state = {"messages": [HumanMessage(content=user_input)]}

    # 2. Execution
    final_state = await graph.ainvoke(initial_state)

    # 3. Assertions
    assert "final_response" in final_state
    response_text = final_state["final_response"]
    response_lower = response_text.lower()

    # Check for key elements in the final, formatted response
    assert "báo giá chi tiết" in response_lower
    assert "gỗ óc chó" in response_lower
    assert "tổng chi phí" in response_lower
    # Check that it selected the correct variant based on the budget
    assert "loại 2" in response_text
    assert "loại 1" not in response_text
    # Check for the calculated total cost
    assert "75,000,000" in response_text

    print(f"Test passed. Final Response:\n{response_text}")

@pytest.mark.asyncio
async def test_full_detailed_quote_flow_budget_too_low():
    """
    Tests the full 'single_step' flow when the budget is insufficient.
    """
    print("\n--- Testing Full Detailed Quote Flow (Budget Too Low) ---")
    
    # 1. Setup
    # Budget is 50,000,000 for 50m2, which is 1,000,000/m2.
    # This is too low for any oak variant in `data_new/gỗ_prices.json`.
    user_input = "Báo giá cho tôi 50m2 gỗ sồi với ngân sách 50 triệu"
    initial_state = {"messages": [HumanMessage(content=user_input)]}

    # 2. Execution
    final_state = await graph.ainvoke(initial_state)

    # 3. Assertions
    assert "final_response" in final_state
    response_text = final_state["final_response"]

    # The tool should return a helpful message, which gets passed to the response generator.
    assert "rất tiếc" in response_text.lower()
    assert "không có loại vật liệu" in response_text
    assert "phù hợp với ngân sách" in response_text
    assert "1,000,000" in response_text # Check for budget per sqm
    
    print(f"Test passed. Correctly handled insufficient budget in the flow.")
    print(f"Final Response: {response_text}") 