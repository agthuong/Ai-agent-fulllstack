import pytest
import json
from langchain_core.messages import SystemMessage

from react_agent.prompts import CENTRAL_ROUTER_PROMPT
from react_agent.utils import load_chat_model, cleanup_llm_output

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="module")
def model():
    """Fixture to load the model once per test module."""
    return load_chat_model("qwen3:30b")

async def test_routing_for_super_tool_simple_query(model):
    """
    Tests if the router correctly identifies a simple request
    that should be handled by a super-tool.
    """
    # 1. Setup
    user_input = "So sánh giá gỗ sồi trên thị trường với giá của công ty"
    chat_history = ""

    prompt = CENTRAL_ROUTER_PROMPT.format(
        input=user_input,
        chat_history=chat_history
    )

    # 2. Execution
    raw_response = await model.ainvoke([SystemMessage(content=prompt)])
    cleaned_response = cleanup_llm_output(raw_response.content)

    print(f"\nModel Raw Response:\n---\n{raw_response.content}\n---")
    print(f"Cleaned Response:\n---\n{cleaned_response}\n---")

    # 3. Assertion
    try:
        decision = json.loads(cleaned_response)
    except json.JSONDecodeError:
        pytest.fail(f"The cleaned response is not valid JSON: {cleaned_response}")

    assert isinstance(decision, dict)
    assert "route" in decision
    assert "tool_name" in decision
    assert "args" in decision

    assert decision["route"] == "super_tool"
    assert decision["tool_name"] == "run_market_comparison"
    assert isinstance(decision["args"], dict)
    assert "material" in decision["args"]
    assert "sồi" in decision["args"]["material"] # Check for keyword

async def test_routing_for_complex_query(model):
    """
    Tests if the router correctly identifies a complex request
    that requires planning (ReAct).
    """
    # 1. Setup
    user_input = "Hãy so sánh giá của gỗ sồi và gỗ óc chó, sau đó chọn loại rẻ hơn để báo giá chi tiết cho diện tích sàn 50m2."
    chat_history = ""

    prompt = CENTRAL_ROUTER_PROMPT.format(
        input=user_input,
        chat_history=chat_history
    )

    # 2. Execution
    raw_response = await model.ainvoke([SystemMessage(content=prompt)])
    cleaned_response = cleanup_llm_output(raw_response.content)

    print(f"\nModel Raw Response:\n---\n{raw_response.content}\n---")
    print(f"Cleaned Response:\n---\n{cleaned_response}\n---")

    # 3. Assertion
    try:
        decision = json.loads(cleaned_response)
    except json.JSONDecodeError:
        pytest.fail(f"The cleaned response is not valid JSON: {cleaned_response}")

    assert isinstance(decision, dict)
    assert "route" in decision
    assert decision["route"] == "plan"
    assert "tool_name" not in decision # Should not have tool_name for 'plan' route
    assert "args" not in decision # Should not have args for 'plan' route

async def test_routing_for_conversational_query(model):
    """
    Tests if the router correctly identifies a simple conversational message.
    """
    # 1. Setup
    user_input = "Chào bạn, bạn có thể giúp gì cho tôi?"
    chat_history = ""

    prompt = CENTRAL_ROUTER_PROMPT.format(
        input=user_input,
        chat_history=chat_history
    )

    # 2. Execution
    raw_response = await model.ainvoke([SystemMessage(content=prompt)])
    cleaned_response = cleanup_llm_output(raw_response.content)

    print(f"\nModel Raw Response:\n---\n{raw_response.content}\n---")
    print(f"Cleaned Response:\n---\n{cleaned_response}\n---")

    # 3. Assertion
    try:
        decision = json.loads(cleaned_response)
    except json.JSONDecodeError:
        pytest.fail(f"The cleaned response is not valid JSON: {cleaned_response}")

    assert isinstance(decision, dict)
    assert "route" in decision
    assert decision["route"] == "converse" 