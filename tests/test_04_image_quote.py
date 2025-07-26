import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

from react_agent.graph import graph
from react_agent.state import State

@pytest.mark.asyncio
async def test_full_image_quote_flow():
    """
    Tests the full 'single_step' flow for an image quote request.
    It verifies that the agent can route, execute the run_image_quote tool,
    and generate a final response.
    """
    print("\n--- Testing Full Image Quote Flow (Single-Step) ---")
    
    # 1. Setup: State with an image report in history
    image_report = "Material: Wood - Type: Oak - Position: Floor"
    messages = [
        SystemMessage(content=f"[IMAGE REPORT]:\n{image_report}"),
        HumanMessage(content="Báo giá cho ảnh này")
    ]
    initial_state = {"messages": messages}

    # 2. Execution
    # We use a mock to avoid actual LLM calls and tool execution where possible,
    # but for this integration test, we let the graph run.
    # The key is to see if the nodes connect correctly.
    final_state = await graph.ainvoke(initial_state)

    # 3. Assertions
    assert "final_response" in final_state
    response_text = final_state["final_response"].lower()

    # Check if the final response contains the expected quote information
    assert "báo giá dựa trên hình ảnh" in response_text
    assert "gỗ" in response_text
    assert "sồi" in response_text
    assert "vnd/m²" in response_text # Check for price unit

    print(f"Test passed. Final response contains expected image quote details.")
    print(f"Final Response: {final_state['final_response']}")

@pytest.mark.asyncio
async def test_image_quote_flow_without_report():
    """
    Tests the flow when an image quote is requested but no report exists.
    """
    print("\n--- Testing Image Quote Flow (No Report) ---")
    
    # 1. Setup
    messages = [HumanMessage(content="Báo giá cho ảnh tôi vừa gửi")]
    initial_state = {"messages": messages}

    # 2. Execution
    final_state = await graph.ainvoke(initial_state)

    # 3. Assertions
    assert "final_response" in final_state
    response_text = final_state["final_response"]

    # The tool itself should return a helpful message, which gets passed to the response generator.
    assert "Không tìm thấy báo cáo hình ảnh" in response_text
    assert "Vui lòng tải lên một hình ảnh" in response_text
    
    print(f"Test passed. Correctly handled missing image report in the flow.")
    print(f"Final Response: {response_text}") 