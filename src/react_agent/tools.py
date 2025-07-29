"""
Defines the unified, foundational tools for the agent.
All tools are gathered here to create a single, consistent toolset.
"""
import asyncio
import base64
import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_tavily import TavilySearch
from langchain_community.tools.tavily_search import TavilySearchResults
import itertools
import traceback

from react_agent.configuration import Configuration
from react_agent.memory import memory_manager
from react_agent.vision import get_gemini_vision_report

# Tích hợp các module báo giá mới
from react_agent.quote_parser import parse_image_report, format_components_for_display
from react_agent.quote_generator import (
    generate_preliminary_quote,
    generate_area_quote,
    generate_budget_quote,
    parse_area,
    parse_budget,
    calculate_optimal_combinations # Import the new function
)

# --- Path setup for data files ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
_data_dir = os.path.join(_current_dir, '..', '..', 'data_new')

# Create directory to save quotes if it doesn't exist
QUOTES_DIR = "saved_quotes"
os.makedirs(QUOTES_DIR, exist_ok=True)

# --- Constants ---
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data_new')
MARKET_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'market_data')

# Sửa mapping để phù hợp với file trong data_new
VIETNAMESE_MATERIAL_MAP = {
    "gỗ": "wood",
    "sơn": "paint",
    "đá": "stone",
    "giấy dán tường": "wallpaper"
}

# Mapping cho các loại (type) cụ thể, giúp chuẩn hóa input của người dùng
VIETNAMESE_TYPE_MAP = {
    # Gỗ
    "sồi": "Sồi",
    "sồi mỹ": "Sồi",
    "oak": "Sồi",
    "gõ đỏ": "Gõ Đỏ",
    "óc chó": "Óc Chó",
    "walnut": "Óc Chó",
    # Đá
    "marble": "Marble",
    "cẩm thạch": "Marble",
    "granite": "Granite",
    "hoa cương": "Granite",
    # Sơn
    "sơn màu": "color paint",
    "màu sơn": "color paint",
    "sơn hiệu ứng": "Effect paint",
    "sơn chống thấm": "Waterproof paint",
}

# --- Constants for Area Distribution ---
POSITION_GROUP_MAP = {
    "tường": ["tường", "wall"],
    # Add other groups if needed, e.g., "phòng": ["phòng", "room"]
}

# --- Data Loading & Parsing Utilities (Core Logic) ---

def get_available_materials_string() -> str:
    """
    Reads all material data and formats it into a catalog string for the Gemini vision prompt.
    This is a critical function to provide context to the vision model.
    """
    material_details = []
    for material_vn, filename_en in VIETNAMESE_MATERIAL_MAP.items():
        file_path = os.path.join(DATA_DIR, f"{filename_en}.json")
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Đọc các loại (type) trực tiếp từ cấu trúc JSON
                if isinstance(data, dict):
                    types = list(data.keys())
                    types_str = ", ".join([f"'{t}'" for t in types])
                    material_details.append(f"- {material_vn} (types: {types_str})")
                else:
                    print(f"Warning: Unexpected data format in {file_path}")
        except Exception as e:
            print(f"Error loading material data from {file_path}: {e}")
            continue # Skip corrupted or malformed files

    print(f"Available materials catalog: {material_details}")
    return "\n".join(material_details)

def _parse_price(price_str: str) -> Optional[float]:
    """Extracts a numerical price from a string like '1,800,000 VND/m^2'."""
    try:
        cleaned_price = re.sub(r'[^\d,]', '', str(price_str)).replace(',', '')
        return float(cleaned_price)
    except (ValueError, TypeError):
            return None

def _load_json_data(material_type: str) -> Optional[List[Dict[str, Any]]]:
    """Loads material data from a JSON file based on the Vietnamese material type."""
    # Chuẩn hóa input của người dùng
    material_type_lower = material_type.lower()
    filename_en = VIETNAMESE_MATERIAL_MAP.get(material_type_lower)

    if not filename_en: return None
    
    file_path = os.path.join(DATA_DIR, f"{filename_en}.json")
    if not os.path.exists(file_path): return None
        
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _parse_image_report(report_text: str) -> List[Dict[str, Optional[str]]]:
    """
    Parses the JSON response from a Gemini vision report into a list of items.
    This version handles JSON format for better reliability.
    """
    items = []
    
    # Clean the input text first
    cleaned_text = report_text.strip()
    
    try:
        # Try to parse as JSON first
        import json
        data = json.loads(cleaned_text)
        
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    material_type = item.get('material', '').strip()
                    specific_type = item.get('type')
                    position = item.get('position', '').strip()
                    
                    # Skip if material is not identified
                    if "không xác định" in material_type.lower():
                        continue
                    
                    # Handle null type
                    if specific_type is None or specific_type == "null":
                        specific_type = None
                    elif isinstance(specific_type, str) and specific_type.lower() in ['null', 'none', '']:
                        specific_type = None
                    elif isinstance(specific_type, str) and "không xác định" in specific_type.lower():
                        specific_type = None

                    final_item = {
                        "material_type": material_type,
                        "type": specific_type,
                        "position": position
                    }
                    items.append(final_item)
        
        return items
        
    except json.JSONDecodeError:
        # Fallback to old text parsing if JSON fails
        return _parse_image_report_text_fallback(cleaned_text)
    except Exception as e:
        print(f"Error parsing image report: {e}")
        return []

def _parse_image_report_text_fallback(report_text: str) -> List[Dict[str, Optional[str]]]:
    """
    Fallback parser for old text format if JSON parsing fails.
    """
    items = []
    
    # Split by newlines to handle each material entry separately
    lines = report_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or not line.startswith('Material:'):
            continue
            
        # Parse each line with the pattern: Material: X - Type: Y - Position: Z - InStock: W
        pattern = re.compile(
            r"Material:\s*(?P<material>.*?)\s*-\s*Type:\s*(?P<type>.*?)\s*-\s*Position:\s*(?P<position>.*?)(?:\s*-\s*InStock:\s*(?P<instock>.*?))?$"
        )
        
        match = pattern.match(line)
        if match:
            material_type = match.group('material').strip()
            specific_type = match.group('type').strip()
            position = match.group('position').strip()
            
            # Skip if material is not identified
            if "không xác định" in material_type.lower():
                continue
                
            # Handle null/empty type
            if specific_type.lower() in ['null', 'none', '']:
                specific_type = None
            elif "không xác định" in specific_type.lower():
                specific_type = None

            items.append({
                "material_type": material_type,
                "type": specific_type,
                "position": position
            })
    
    return items

def _get_preliminary_quotes(items: List[Dict[str, Any]]) -> str:
    """
    Core logic to get price ranges for a list of items, now processing each item
    individually and including its position in the output table. No more grouping.
    """
    print(f"===== _get_preliminary_quotes (Detailed) STARTED with {len(items)} items =====")
    results = []

    # Process each component individually without grouping
    for item in items:
        material_type = item.get("material_type", "N/A")
        specific_type = item.get("type")
        position = item.get("position", "N/A")

        # Standardize type from user input if needed
        if specific_type:
            specific_type = VIETNAMESE_TYPE_MAP.get(specific_type.lower(), specific_type)

        print(f"Processing: Material='{material_type}', Type='{specific_type}', Position='{position}'")

        filename_en = VIETNAMESE_MATERIAL_MAP.get(material_type.lower())
        if not filename_en:
            price_range_str = "Không có dữ liệu"
        else:
            file_path = os.path.join(DATA_DIR, f"{filename_en}.json")
            if not os.path.exists(file_path):
                price_range_str = "Không có dữ liệu"
            else:
                try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        # Get prices for the specific type or all types
                        prices = []
                        target_data = data.get(specific_type) if specific_type else data

                        if specific_type and target_data:
                            # It's a dict of variants
                            prices.extend(target_data.values())
                        elif not specific_type:
                            # It's a dict of types
                            for type_data in target_data.values():
                                prices.extend(type_data.values())

                        if prices:
                            # For simplicity, we just show the first and last price string
                            price_range_str = f"{prices[0]} - {prices[-1]}" if len(prices) > 1 else prices[0]
                        else:
                            price_range_str = "Chưa có giá chi tiết"

                except Exception as e:
                        print(f"Error processing material '{material_type}': {e}")
                        price_range_str = "Lỗi xử lý dữ liệu"

                results.append(f"| {material_type.title()} | {specific_type or 'Tất cả'} | {position.title()} | {price_range_str} |")

    header = "| Vật liệu | Loại | Vị trí | Đơn giá (Ước tính) |\n|---|---|---|---|"
    final_result = header + "\n" + "\n".join(results)
    print(f"===== _get_preliminary_quotes COMPLETED. Result: \n{final_result} =====")
    return final_result

# ==============================================================================
# === NEW, REFACTORED, SINGLE-RESPONSIBILITY TOOLS =============================
# ==============================================================================

@tool
def get_internal_price(material_type: str, specific_type: Optional[str] = None, mode: str = 'range') -> str:
    """
    (Giá nội bộ) Tra cứu giá của một vật liệu cụ thể từ cơ sở dữ liệu của công ty.
    Sử dụng khi người dùng hỏi giá trực tiếp cho một sản phẩm.

    Args:
        material_type: Loại vật liệu (ví dụ: 'gỗ', 'đá', 'sơn').
        specific_type: Loại cụ thể (ví dụ: 'Oak', 'Marble').
        mode: 'range' (mặc định) trả về khoảng giá, 'full_list' trả về danh sách đầy đủ.
    """
    # This logic is extracted from the old `material_price_query` tool.
    MATERIAL_FILENAME_MAP = {
        'sơn': 'paint.json', 'gỗ': 'wood.json', 'đá': 'stone.json', 'giấy dán tường': 'wallpaper.json'
    }
    lookup_key = material_type.lower()
    if lookup_key not in MATERIAL_FILENAME_MAP:
        return f"Lỗi: Loại vật liệu '{material_type}' không được hỗ trợ."

    filename = os.path.join(_data_dir, MATERIAL_FILENAME_MAP[lookup_key])
    if not os.path.exists(filename):
        return f"Lỗi: Không tìm thấy file dữ liệu cho '{material_type}'."

    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)

    target_data = {}
    if specific_type:
        # If a specific type is given, find it (case-insensitive)
        type_found = False
        for key in data:
            if key.lower() == specific_type.lower():
                target_data = {key: data[key]}
                type_found = True
                break
        if not type_found:
            return f"Không tìm thấy loại cụ thể '{specific_type}' trong danh mục '{material_type}'."
    else:
        # CORRECTION: If no specific_type, use all types for that material
        target_data = data

    if mode == 'full_list':
        # ... (logic for full_list) ...
        return "Full list logic here."

    all_prices = []
    for details in target_data.values():
        if isinstance(details, dict):
            for price_str in details.values():
                try:
                    price_val = float(re.match(r'[\d,.]+', price_str.replace(',', '')).group(0))
                    all_prices.append(price_val)
                except (ValueError, AttributeError):
                    continue
    
    if not all_prices:
        return f"Không có dữ liệu giá cho '{specific_type or material_type}'"

    min_price = min(all_prices)
    max_price = max(all_prices)
    
    type_name = specific_type or f"các loại {material_type}"
    return f"Giá thi công cho {type_name} dao động từ {min_price:,.0f} VND/m² đến {max_price:,.0f} VND/m²."


@tool
def generate_quote_from_image(image_report: str) -> str:
    """
    (Nội bộ) Phân tích báo cáo từ ảnh (do Vision AI cung cấp) và tạo báo giá sơ bộ.
    Chỉ sử dụng khi người dùng bắt đầu bằng việc gửi một hình ảnh.
    """
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info(f"[DEBUG] image_report input: {repr(image_report)}")
    components = _parse_image_report(image_report)
    logger.info(f"[DEBUG] components parsed: {components}")
    if not components:
        logger.warning(f"[DEBUG] No components parsed from image_report: {repr(image_report)}")
        # Vẫn trả về bảng giá rỗng thay vì lỗi
        return "# Báo Giá Sơ Bộ\n\nKhông có vật liệu nào được nhận diện từ hình ảnh. Vui lòng kiểm tra lại ảnh hoặc thử lại với ảnh khác."
    return generate_preliminary_quote(components)


@tool
async def propose_options_for_budget(items: List[Dict[str, Any]], budget: float) -> str:
    """
    (Nội bộ) Đề xuất các phương án vật liệu tối ưu cho một hoặc nhiều hạng mục dựa trên diện tích và tổng ngân sách.
    Sử dụng khi người dùng cung cấp cả diện tích và ngân sách.
    """
    print(f"--- Running Tool: propose_options_for_budget for {len(items)} items ---")
    
    # This is placeholder logic. You'll need to implement the full logic.
    return "Optimal combination proposal based on budget."


@tool
async def get_market_price(material: str) -> List[Dict[str, str]]:
    """
    (Giá thị trường) Tìm kiếm giá thị trường của một vật liệu bằng Tavily Search API.
    Sử dụng để lấy dữ liệu từ bên ngoài, so sánh với giá nội bộ. Trả về một DANH SÁCH (list) các kết quả.
    """
    print(f"--- INFO: Searching market price for '{material}' via Tavily ---")
    try:
        search_tool = TavilySearchResults(max_results=3)
        query = f"giá thị trường hiện tại của {material} ở Việt Nam"
        raw_results = await search_tool.ainvoke(query)
        
        # Sanitize and simplify the results
        sanitized_results = _sanitize_for_json(raw_results)

        simplified_results = []
        if isinstance(sanitized_results, list):
            for res in sanitized_results:
                if isinstance(res, dict):
                    simplified_results.append({
                        "title": res.get("title", "N/A"),
                        "url": res.get("url", "N/A"),
                        "content": res.get("content", "N/A")
                    })
        
        # CORRECTION: Return the list of dicts directly, not a JSON string
        return simplified_results
    except Exception as e:
        print(f"Error during Tavily search: {e}\n{traceback.format_exc()}")
        # Return an error structure that is also a list of dicts
        return [{"error": f"Lỗi khi tìm kiếm giá thị trường qua Tavily: {e}"}]

# --- Tools for Memory/Quote Management ---

@tool
def get_saved_quotes(project_name: Optional[str] = None) -> str:
    """(Nội bộ) Lấy danh sách các báo giá đã lưu hoặc nội dung của một báo giá cụ thể."""
    if project_name:
        filename = os.path.join(QUOTES_DIR, f"{project_name}.txt")
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            return f"Không tìm thấy báo giá nào với tên '{project_name}'."
    else:
        try:
            files = os.listdir(QUOTES_DIR)
            if not files:
                return "Chưa có báo giá nào được lưu."
            
            quote_names = [f.replace('.txt', '') for f in files if f.endswith('.txt')]
            return "Các báo giá đã lưu:\n- " + "\n- ".join(quote_names)
        except FileNotFoundError:
            return "Chưa có báo giá nào được lưu."


@tool
def save_quote_to_file(project_name: str, content: str) -> str:
    """(Nội bộ) Lưu một báo giá vào file với tên dự án được chỉ định."""
    try:
        filename = os.path.join(QUOTES_DIR, f"{project_name}.txt")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Quote successfully saved as '{project_name}.txt'"
    except Exception as e:
        return f"Error saving quote: {e}"

# --- Helper function to ensure all parts of the result are JSON serializable
def _sanitize_for_json(data):
    if isinstance(data, dict):
        return {str(k): _sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_sanitize_for_json(item) for item in data]
    elif isinstance(data, (str, int, float, bool)) or data is None:
        return data
    else:
        return str(data)

# ==============================================================================
# === HELPER FUNCTIONS (Previously in super_tools.py) ==========================
# ==============================================================================

def _parse_area(area_str: str) -> float:
    """
    Parses an area string with various formats and units, returning the area in square meters (m²).
    """
    normalized_str = str(area_str).lower().replace("mét vuông", "m2").replace("vuông", "m2")
    numbers = re.findall(r'(\d+\.?\d*)', normalized_str)
    if not numbers:
        raise ValueError(f"Could not extract a numerical value from area string: '{area_str}'")
    value = float(numbers[0])
    if "cm2" in normalized_str or "cm" in normalized_str:
        return value / 10000
    return value

async def _get_all_variants_for_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Helper to get all variants and prices for a single material item."""
    material_type = item.get("material_type")
    item_type = item.get("type")
    
    full_list_input = {"material_type": material_type, "type": item_type, "mode": "full_list"}
    full_list_result = await get_internal_price.ainvoke(full_list_input)
    
    # This is placeholder logic. You'll need to implement the full logic for parsing.
    return [{"variant": "some_variant", "price": 123.0, "area": 1.0, "material": "some_material"}]

# --- Unified Tools List ---

TOOLS = {
    "get_internal_price": get_internal_price,
    "generate_quote_from_image": generate_quote_from_image,
    "propose_options_for_budget": propose_options_for_budget,
    "get_market_price": get_market_price,
    "get_saved_quotes": get_saved_quotes,
    "save_quote_to_file": save_quote_to_file,
}

# This function is now the robust tool dispatcher
async def execute_tool(tool_name: str, tool_args: dict) -> str:
    """
    Executes the appropriate tool by trying async first, then falling back to sync.
    """
    if tool_name in TOOLS:
        selected_tool = TOOLS[tool_name]
        try:
            return await selected_tool.ainvoke(tool_args)
        except NotImplementedError:
            print(f"--- INFO: Tool '{tool_name}' is synchronous. Falling back to .invoke() ---")
            return selected_tool.invoke(tool_args)
        except Exception as e:
            return f"Lỗi khi thực thi công cụ '{tool_name}': {e}"
    return f"Công cụ '{tool_name}' không được tìm thấy."