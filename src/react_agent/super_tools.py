"""
Super-Tools for the Hybrid Agent.

These tools encapsulate the core business logic for each predefined task.
They are called by the "super_tool_executor" node when the router decides
on a "super_tool" route. They are designed to be flexible and handle
multiple items where applicable.
"""
import asyncio
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool

# Import the basic tools that super-tools will orchestrate
from .base_tools import material_price_query, search
from .prompts import RESPONSE_PROMPT # This might be needed for more complex synthesis later

# === Helper Functions for Super-Tools ===

def _parse_area(area_str: str) -> float:
    """
    Parses an area string with various formats and units, returning the area in square meters (m²).
    Handles formats like: "30m2", "50 mét vuông", "10000 cm2".
    """
    # Normalize the string
    normalized_str = area_str.lower()
    normalized_str = normalized_str.replace("mét vuông", "m2").replace("vuông", "m2")
    
    # Find the numerical value
    numbers = re.findall(r'(\d+\.?\d*)', normalized_str)
    if not numbers:
        raise ValueError(f"Could not extract a numerical value from the area string: '{area_str}'")
    
    value = float(numbers[0])
    
    # Convert units to square meters
    if "cm2" in normalized_str or "cm" in normalized_str:
        return value / 10000  # Convert cm² to m²
    
    # Default to m² if no specific unit is found
    return value


def _parse_image_report(report_text: str) -> List[Dict[str, Optional[str]]]:
    """
    Parses the structured text from a Gemini vision report into a list of items.
    """
    items = []
    pattern = re.compile(r"Material:\s*(?P<material>.*?)\s*-\s*Type:\s*(?P<type>.*?)\s*-")
    
    for line in report_text.splitlines():
        match = pattern.search(line)
        if match:
            material_type = match.group('material').strip()
            specific_type = match.group('type').strip()
            
            if "không xác định" in material_type.lower():
                continue

            items.append({
                "material_type": material_type,
                "type": specific_type if "không xác định" not in specific_type.lower() else None
            })
    return items

def _parse_full_price_list(price_list_str: str) -> List[Dict[str, Any]]:
    """
    Parses the detailed price list string from material_price_query(mode='full_list')
    into a structured list of variants with their prices.
    """
    variants = []
    price_pattern = re.compile(r"([\d,]+)")
    
    for line in price_list_str.splitlines():
        if ":" in line:
            parts = line.split(":")
            variant_name = parts[0].strip().lstrip("- ").strip()
            price_match = price_pattern.search(parts[1])
            if variant_name and price_match:
                price_str = price_match.group(1).replace(",", "")
                try:
                    variants.append({"variant": variant_name, "price": float(price_str)})
                except ValueError:
                    continue
    return variants

# === Super-Tool Implementations ===

@tool
async def run_preliminary_quote(items: List[Dict[str, Optional[str]]]) -> str:
    """
    Handles the business logic for a preliminary quote for one or more items.
    Provides a price range for each material specified.
    """
    print(f"--- Running Super-Tool: run_preliminary_quote for {len(items)} items ---")
    
    tasks = []
    for item in items:
        tool_input = {"material_type": item.get("material_type"), "type": item.get("type"), "mode": "range"}
        tasks.append(material_price_query.ainvoke(tool_input))
    
    results = await asyncio.gather(*tasks)
    return "\n".join(results)

@tool
async def run_market_comparison(items: List[Dict[str, Optional[str]]]) -> str:
    """
    Handles the business logic for comparing company vs. market prices for one or more items.
    """
    print(f"--- Running Super-Tool: run_market_comparison for {len(items)} items ---")

    async def compare_item(item):
        material_type = item.get("material_type", "")
        item_type = item.get("type", "")
        
        company_price_input = {"material_type": material_type, "type": item_type, "mode": "range"}
        company_price_result = await material_price_query.ainvoke(company_price_input)
        
        search_term = item_type or material_type
        search_query = f"Giá thi công {search_term} trên thị trường"
        market_price_result = await search.ainvoke({"query": search_query})

        return f"Comparison for '{search_term}':\n- Company Installation Price: {company_price_result}\n- Market Installation Price: {market_price_result}"

    tasks = [compare_item(item) for item in items]
    results = await asyncio.gather(*tasks)
    return "\n\n".join(results)

@tool
async def run_image_quote(messages: List[Any]) -> str:
    """
    Handles the business logic for quoting from an image.
    It finds the most recent image report in the conversation and provides a preliminary quote for the identified materials.
    """
    print(f"--- Running Super-Tool: run_image_quote ---")
    
    report_text = None
    for msg in reversed(messages):
        content_str = str(msg.content)
        if isinstance(msg, SystemMessage) and "[IMAGE REPORT]:" in content_str:
            report_text = content_str.split("[IMAGE REPORT]:", 1)[1].strip()
            break
            
    if not report_text:
        return "Không tìm thấy báo cáo hình ảnh nào trong ngữ cảnh gần đây. Vui lòng tải lên một hình ảnh để được báo giá."

    items_to_quote = _parse_image_report(report_text)
    
    if not items_to_quote:
        return "Không thể xác định được vật liệu nào từ hình ảnh. Vui lòng thử một hình ảnh khác rõ ràng hơn."

    quote_results = await run_preliminary_quote(items_to_quote)
    return f"Báo giá dựa trên hình ảnh:\n{quote_results}"

@tool
async def run_detailed_quote(items: List[Dict[str, Optional[str]]], area: str, budget: float) -> str:
    """
    Handles the business logic for a detailed quote.
    'area' is a string that can include units, e.g., "30m2", "50 mét vuông".
    """
    print(f"--- Running Super-Tool: run_detailed_quote ---")
    
    try:
        normalized_area = _parse_area(area)
    except ValueError as e:
        return f"Lỗi xử lý diện tích: {e}. Vui lòng cung cấp diện tích hợp lệ."

    if not items:
        return "Lỗi: Không có vật liệu nào được chỉ định để báo giá chi tiết."
    
    item = items[0]
    material_type = item.get("material_type")
    specific_type = item.get("type")
    
    full_list_input = {"material_type": material_type, "type": specific_type, "mode": "full_list"}
    full_list_result = await material_price_query.ainvoke(full_list_input)
    
    all_variants = _parse_full_price_list(full_list_result)
    if not all_variants:
        return f"Không tìm thấy danh sách giá chi tiết cho '{specific_type or material_type}'."
        
    budget_per_sqm = budget / normalized_area
    valid_options = [v for v in all_variants if v["price"] <= budget_per_sqm]
    
    if not valid_options:
        min_price = min(v['price'] for v in all_variants) if all_variants else 0
        return (f"Rất tiếc, không có loại vật liệu '{specific_type or material_type}' nào phù hợp với ngân sách "
                f"{budget:,.0f} VND cho diện tích {area} m².\n"
                f"Ngân sách của bạn tương đương {budget_per_sqm:,.0f} VND/m², trong khi lựa chọn rẻ nhất có giá "
                f"{min_price:,.0f} VND/m².")

    best_option = max(valid_options, key=lambda x: x["price"])
    
    final_price_per_sqm = best_option["price"]
    total_cost = final_price_per_sqm * normalized_area
    
    return (f"Báo giá chi tiết cho '{material_type}':\n"
            f"- Lựa chọn phù hợp nhất với ngân sách: {best_option['variant']}\n"
            f"- Diện tích: {area} m²\n"
            f"- Đơn giá thi công: {final_price_per_sqm:,.0f} VND/m²\n"
            f"- **Tổng chi phí:** {total_cost:,.0f} VND (Trong ngân sách {budget:,.0f} VND)")

# === Map for the Router ===

SUPER_TOOLS_MAP = {
    "run_preliminary_quote": run_preliminary_quote,
    "run_market_comparison": run_market_comparison,
    "run_image_quote": run_image_quote,
    "run_detailed_quote": run_detailed_quote,
    # "run_quote_management" will be implemented next
} 