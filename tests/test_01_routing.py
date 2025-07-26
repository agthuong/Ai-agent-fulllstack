import pytest
import json
from langchain_core.messages import HumanMessage, SystemMessage

from react_agent.graph import central_router_node
from react_agent.state import State
from react_agent.utils import load_chat_model, cleanup_llm_output
from react_agent.prompts import CENTRAL_ROUTER_PROMPT
from react_agent.tools import TOOLS

# Load the model once for all tests in this module
model = load_chat_model("qwen2:1.5b-instruct-q4_0")

@pytest.mark.asyncio
async def test_routing_to_single_step_simple():
    """Tests if the router correctly identifies a simple, single-tool request."""
    print("\n--- Testing Single-Step Routing (Simple) ---")
    user_input = "Giá gỗ sồi là bao nhiêu?"
    state = State(messages=[HumanMessage(content=user_input)])

    router_output = await central_router_node(state)

    assert router_output["route"] == "single_step"
    assert router_output["tool_name"] == "run_preliminary_quote"
    assert "items" in router_output["tool_args"]
    assert len(router_output["tool_args"]["items"]) == 1
    assert router_output["tool_args"]["items"][0]["material_type"] == "gỗ"
    print("Test passed: Correctly routed to single_step for simple query.")

@pytest.mark.asyncio
async def test_routing_to_single_step_detailed():
    """Tests if the router correctly identifies a detailed quote request as a single-step."""
    print("\n--- Testing Single-Step Routing (Detailed) ---")
    user_input = "Báo giá cho tôi 50m2 gỗ óc chó với ngân sách 80 triệu"
    state = State(messages=[HumanMessage(content=user_input)])

    router_output = await central_router_node(state)

    assert router_output["route"] == "single_step"
    assert router_output["tool_name"] == "run_detailed_quote"
    assert "items" in router_output["tool_args"]
    assert "area" in router_output["tool_args"]
    assert "budget" in router_output["tool_args"]
    assert router_output["tool_args"]["area"] == "50m2"
    assert router_output["tool_args"]["budget"] == 80000000.0
    print("Test passed: Correctly routed to single_step for detailed quote.")

@pytest.mark.asyncio
async def test_routing_to_multi_step():
    """Tests if the router correctly identifies a complex request requiring a plan."""
    print("\n--- Testing Multi-Step Routing ---")
    user_input = "Báo giá sơn cho phòng khách 30m2 và phòng ngủ 20m2 với tổng ngân sách 50 triệu"
    state = State(messages=[HumanMessage(content=user_input)])
    
    router_output = await central_router_node(state)

    assert router_output["route"] == "multi_step"
    assert "tool_name" not in router_output # Should not decide tool at this stage
    assert "tool_args" not in router_output
    print("Test passed: Correctly routed to multi_step for complex query.")

@pytest.mark.asyncio
async def test_routing_to_converse():
    """Tests if the router correctly identifies a conversational message."""
    print("\n--- Testing Conversational Routing ---")
    user_input = "Cảm ơn bạn nhiều"
    state = State(messages=[HumanMessage(content=user_input)])

    router_output = await central_router_node(state)

    assert router_output["route"] == "converse"
    print("Test passed: Correctly routed to converse for conversational input.") 