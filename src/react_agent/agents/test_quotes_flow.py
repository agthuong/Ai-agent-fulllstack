import pytest
from ..state import State
from .planner import planner_node, history_summarizer_node
from .executor import executor_node
from .responder import responder_node
import asyncio

@pytest.mark.asyncio
async def test_quotes_flow():
    # 1. Giả lập state ban đầu với area_map
    state = State(
        messages=[],
        history_summary="",
        plan=None,
        tool_results=None,
        area_map={"sàn": {"position": "sàn", "area": 72, "material_type": "Sàn gỗ"}},
        quotes=[]
    )
    # 2. Giả lập planner tạo plan với subtask báo giá
    plan = ["Step 1: Tra cứu giá nội bộ cho sàn (Sàn - Sàn gỗ, 72m²)"]
    state["plan"] = plan
    # 3. Executor thực hiện báo giá lần đầu
    result1 = await executor_node(state)
    assert result1["quotes"], "Quotes phải được cập nhật sau khi báo giá"
    quotes_after_1st = result1["quotes"]
    # 4. Executor thực hiện lại cùng subtask, phải lấy từ quotes, không gọi lại tool
    result2 = await executor_node({**state, "quotes": quotes_after_1st})
    assert result2["quotes"] == quotes_after_1st, "Quotes không được thay đổi khi đã có báo giá"
    # 5. Responder tổng hợp đúng quotes
    responder_result = await responder_node({**state, "tool_results": result2["tool_results"], "quotes": quotes_after_1st})
    content = responder_result["messages"][-1].content.lower()
    assert any(kw in content for kw in ["sàn", "sàn gỗ"]), "Responder phải trả về thông tin báo giá sàn"

if __name__ == "__main__":
    asyncio.run(test_quotes_flow())