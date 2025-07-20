import pytest
from typing import List, Dict, Optional, Any
import copy

# Import the super-tool directly from its new location
from react_agent.super_tools import run_detailed_quote

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio

# --- Correct Mocking Strategy ---

async def mock_material_price_query_coroutine(material_type: str, type: Optional[str] = None, mode: str = 'range') -> str:
    """
    This mock function has the SAME signature as the original 'material_price_query'
    function that the tool wraps. This is the correct way to mock it.
    """
    print(f"--- MOCK material_price_query called with: material_type='{material_type}', type='{type}', mode='{mode}' ---")
    if mode == "full_list":
        if material_type == "gỗ":
            return """
            - Gỗ Óc Chó loại 1: 1,800,000
            - Gỗ Óc Chó loại 2: 1,500,000
            - Gỗ Sồi Mỹ: 1,200,000
            - Gỗ Sồi Nga: 1,100,000
            """
        else:
            return "Không tìm thấy giá cho vật liệu này"
    return "Unsupported mode for mock"


@pytest.fixture(autouse=True)
def patch_tools(monkeypatch):
    """
    Patches the '.coroutine' attribute of the tool object. This replaces the
    core async function of the tool with our mock, solving the Pydantic error.
    """
    monkeypatch.setattr(
        "react_agent.super_tools.material_price_query.coroutine",
        mock_material_price_query_coroutine
    )

async def test_detailed_quote_success():
    """
    Tests the success scenario where a suitable material is found within budget.
    """
    print("\n--- TEST: Detailed Quote Success ---")
    items: List[Dict[str, Optional[str]]] = [{"material_type": "gỗ", "type": "óc chó"}]
    area = 50.0
    budget = 80_000_000.0  # 80 million

    result = await run_detailed_quote(items=items, area=area, budget=budget)
    
    # Sanitize the result string by removing commas for robust comparison
    result_sanitized = result.replace(",", "")

    assert "Báo giá chi tiết" in result
    assert "Gỗ Óc Chó loại 2" in result
    assert "Tổng chi phí:" in result
    assert "75000000 VND" in result_sanitized # Correctly check for the number without commas

async def test_detailed_quote_budget_too_low():
    """
    Tests the scenario where the budget is too low for any available option.
    """
    print("\n--- TEST: Detailed Quote Budget Too Low ---")
    items: List[Dict[str, Optional[str]]] = [{"material_type": "gỗ", "type": "sồi"}]
    area = 50.0
    budget = 50_000_000.0 # 50 million, which is 1M/m², lower than the cheapest option (1.1M)

    result = await run_detailed_quote(items=items, area=area, budget=budget)
    
    # Sanitize the result string by removing commas for robust comparison
    result_sanitized = result.replace(",", "")

    assert "Rất tiếc" in result
    # Check for key phrases instead of the exact string to make the test less brittle
    assert "không có loại vật liệu" in result
    assert "phù hợp với ngân sách" in result
    assert "1000000 VND/m²" in result_sanitized # Check for budget per sqm
    assert "1100000 VND/m²" in result_sanitized # Check for cheapest option price

async def test_detailed_quote_no_items_provided():
    """
    Tests the edge case where the items list is empty.
    """
    print("\n--- TEST: Detailed Quote No Items Provided ---")
    items: List[Dict[str, Optional[str]]] = []
    area = 50.0
    budget = 100_000_000.0

    result = await run_detailed_quote(items=items, area=area, budget=budget)
    
    assert "Lỗi: Không có vật liệu nào được chỉ định" in result 