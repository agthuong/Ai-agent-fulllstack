import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from react_agent.state import State
from react_agent.tools import run_image_quote

pytestmark = pytest.mark.asyncio

async def test_image_quote_with_report():
    """
    Tests the run_image_quote super-tool when an image report is present in the history.
    """
    # 1. Setup
    image_report = """
    Interior: true
    Material: Wood - Type: Oak - Position: Floor
    Material: Paint - Type: Không xác định - Position: Wall
    Material: Không xác định - Type: Metal - Position: Lamp
    """
    
    messages = [
        HumanMessage(content="Một hình ảnh đã được tải lên"),
        SystemMessage(content=f"[IMAGE REPORT]:\n{image_report}"),
        HumanMessage(content="Báo giá cho các vật liệu trong ảnh này")
    ]
    
    # 2. Execution
    result = await run_image_quote(messages=messages)
    
    # 3. Assertions
    # Convert result to lowercase for case-insensitive matching
    result_lower = result.lower()

    assert "báo giá dựa trên hình ảnh:" in result_lower
    # It should find prices for Wood-Oak and Paint
    assert "giá thi công cho wood - oak" in result_lower
    assert "giá thi công cho paint" in result_lower
    # It should NOT try to find prices for the unidentified material
    assert "không xác định" not in result_lower
    
    print(f"\nTest passed. Image quote result:\n{result}")

async def test_image_quote_without_report():
    """
    Tests the run_image_quote super-tool when no image report is in the recent context.
    """
    # 1. Setup
    messages = [
        HumanMessage(content="Hello there"),
        HumanMessage(content="Báo giá cho các vật liệu trong ảnh của tôi")
    ]
    
    # 2. Execution
    result = await run_image_quote(messages=messages)
    
    # 3. Assertions
    assert "Không tìm thấy báo cáo hình ảnh nào" in result
    assert "Vui lòng tải lên một hình ảnh" in result
    
    print(f"\nTest passed. Correctly handled missing image report.") 