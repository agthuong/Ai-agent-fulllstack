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

from react_agent.configuration import Configuration
from react_agent.memory import memory_manager
from react_agent.vision import get_gemini_vision_report
import itertools

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
    Parses the structured text from a Gemini vision report into a list of items.
    This version is robust and handles multiple entries on a single line.
    """
    items = []
    # This regex finds all occurrences of the Material-Type-Position pattern.
    # It captures the full position string, which will be cleaned up next.
    pattern = re.compile(
        r"Material:\s*(?P<material>.*?)\s*-\s*Type:\s*(?P<type>.*?)\s*-\s*Position:\s*(?P<position>.*?)(?=; Material:|$)"
    )
    
    for match in pattern.finditer(report_text):
        material_type = match.group('material').strip()
        specific_type = match.group('type').strip()
        # Clean the position string by removing any trailing " - InStock..." part.
        position = match.group('position').split(' - InStock:')[0].strip()

        if "không xác định" in material_type.lower():
            continue

        items.append({
            "material_type": material_type,
            "type": specific_type if "không xác định" not in specific_type.lower() else None,
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

@tool
def quote_materials(
    image_report: Optional[str] = None,
    budget: Optional[str] = None,
    area_map: Optional[Dict[str, Any]] = None,
    material_list: Optional[List[Dict[str, Any]]] = None,
    # Deprecated args, kept for compatibility but should not be used by LLM
    material_type: Optional[str] = None,
    type: Optional[str] = None,
) -> str:
    """
    All-in-one material quoting tool. It determines the correct quoting mode based on inputs.
    - Use for image analysis: provide `image_report`.
    - Use for area-based quotes: provide `area_map`.
    - Use for budget-based recommendations: provide `budget` AND `area_map`.
    - Use for simple price checks: provide `material_list`.

    Args:
        image_report: Analysis report from Gemini Vision.
        budget: Budget constraint (e.g., "2 tỉ", "200 tr").
        area_map: Dictionary mapping positions to their areas and material details.
                  Example: {"sàn": {"area": "50m2", "material_type": "gỗ"}, "phòng": {"dimensions": "4x5x3", "material_type": "sơn"}}
        material_list: A direct list of materials for a simple price range check.
                       Example: [{"material_type": "gỗ", "type": "sồi"}]

    Returns:
        A formatted quote or price information string.
    """
    print(f"\n--- TOOL: quote_materials ---\n"
          f"Inputs: image_report={'Yes' if image_report else 'No'}, "
          f"budget='{budget}', area_map={area_map}, material_list={material_list}\n")

    # --- 1. Mode Determination ---
    mode = "price_query" # Default
    if budget and area_map:
        mode = "budget_quote"
    elif area_map:
        mode = "area_map_quote"
    elif image_report:
        mode = "image_quote"
    elif material_list:
        mode = "price_query"
    else:
        return "Lỗi: Không đủ thông tin để xử lý. Vui lòng cung cấp hình ảnh, bản đồ diện tích, hoặc danh sách vật liệu."

    print(f"Determined Mode: {mode}")

    # --- 2. Data Preparation ---
    components = []
    notes = []

    # If there's an image, it serves as the base context for positions
    base_components_from_image = parse_image_report(image_report) if image_report else []

    if area_map:
        # area_map is the primary driver for quoting. It enriches or overrides the base components.
        enriched_components, missing_notes = _enrich_components_from_area_map(base_components_from_image, area_map)
        components = enriched_components
        notes.extend(missing_notes)
    elif image_report:
         # No area_map, just an image. Use components directly from the image report.
        components = base_components_from_image
    elif mode == "price_query" and material_list:
        components = material_list


    # --- 3. Quote Generation ---
    result = ""
    if not components and not notes:
        return "Không thể xác định các hạng mục cần báo giá từ thông tin bạn cung cấp."

    try:
        if mode == "budget_quote":
            budget_val = parse_budget(budget)
            if not components:
                return "Lỗi: Cần có `area_map` để đưa ra đề xuất theo ngân sách."

            # --- REPLACED LOGIC ---
            # The old logic incorrectly divided the budget.
            # The new logic calls a powerful combination finder.
            result = calculate_optimal_combinations(components, budget_val)
            # --- END REPLACED LOGIC ---

        elif mode == "area_map_quote":
            result = generate_area_quote(components)

        elif mode == "image_quote":
            result = generate_preliminary_quote(components)

        elif mode == "price_query":
            result = generate_preliminary_quote(components)

    except Exception as e:
        import traceback
        print(f"ERROR during quote generation: {e}\n{traceback.format_exc()}")
        return f"Đã xảy ra lỗi nội bộ khi tạo báo giá: {e}"

    # --- 4. Final Formatting ---
    if notes:
        result += "\n\n" + "\n".join(notes)

    return result

# ==============================================================================
# === HELPER FUNCTIONS (Previously in super_tools.py) ==========================
# ==============================================================================

def _parse_area(area_str: str) -> float:
    """
    Parses an area string with various formats and units, returning the area in square meters (m²).
    Handles formats like: "30m2", "50 mét vuông", "10000 cm2".
    """
    normalized_str = str(area_str).lower()
    normalized_str = normalized_str.replace("mét vuông", "m2").replace("vuông", "m2")
    
    numbers = re.findall(r'(\d+\.?\d*)', normalized_str)
    if not numbers:
        raise ValueError(f"Could not extract a numerical value from the area string: '{area_str}'")
    
    value = float(numbers[0])
    
    if "cm2" in normalized_str or "cm" in normalized_str:
        return value / 10000
    
    return value

def _parse_full_price_list(price_list_str: str) -> List[Dict[str, Any]]:
    """
    Parses the detailed price list string from material_price_query(mode='full_list')
    into a structured list of variants with their prices and parent type.
    """
    variants = []
    price_pattern = re.compile(r"([\d,]+)")
    current_parent_type = None
    
    for line in price_list_str.splitlines():
        # Check for a new parent type header
        if line.strip().startswith("##"):
            current_parent_type = line.strip().lstrip("## ").strip()
            continue
        
        # Check for a variant line
        if ":" in line:
            parts = line.split(":")
            variant_name = parts[0].strip().lstrip("- ").strip()
            price_match = price_pattern.search(parts[1])
            if variant_name and price_match and current_parent_type:
                price_str = price_match.group(1).replace(",", "")
                try:
                    variants.append({
                        "variant": variant_name,
                        "price": float(price_str),
                        "parent_type": current_parent_type
                    })
                except ValueError:
                    continue
    return variants

# ==============================================================================
# === UNIFIED TOOL IMPLEMENTATIONS =============================================
# ==============================================================================

@tool
def material_price_query(material_type: str, type: Optional[str] = None, mode: str = 'range') -> str:
    """
    Query the price of a specific material from the company's database.

    Args:
        material_type: Category of material (e.g., 'gỗ', 'đá', 'sơn')
        type: Specific variant (e.g., 'Oak', 'Marble', 'Color paint')
        mode: 'range' (default) returns price range, 'full_list' returns complete list

    Returns:
        Price information for the requested material

    Use only when the user wants to know the price of ONE specific material type, without requiring quotes or image analysis.
    """
    MATERIAL_FILENAME_MAP = {
        'sơn': 'paint.json',
        'gỗ': 'wood.json',
        'đá': 'stone.json',
        'giấy dán tường': 'wallpaper.json'
    }
    lookup_key = material_type.lower()
    if lookup_key not in MATERIAL_FILENAME_MAP:
        return f"Lỗi: Loại vật liệu '{material_type}' không được hỗ trợ."

    filename = os.path.join(_data_dir, MATERIAL_FILENAME_MAP[lookup_key])

    if not os.path.exists(filename):
        return f"Lỗi: Không tìm thấy file dữ liệu cho '{material_type}'."

    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # If a specific type is requested (e.g., "Oak"), filter the data to only that type.
    # Otherwise, use all data for the material (e.g., all wood types).
    target_data = {}
    if type:
        # This lookup was case-sensitive. Let's make it case-insensitive.
        type_found = False
        for key in data:
            if key.lower() == type.lower():
                target_data = {key: data[key]}
                type_found = True
                break

        # Fallback logic: If the exact type is not found, try parsing it as "Parent Type - Variant"
        if not type_found and ' - ' in type:
            parsed_type = type.split(' - ')[0].strip()
            print(f"DEBUG: Exact type '{type}' not found. Attempting fallback to parsed parent type '{parsed_type}'.")
            for key in data:
                if key.lower() == parsed_type.lower():
                    target_data = {key: data[key]}
                    type_found = True
                    break
        
        if not type_found:
            return f"Không tìm thấy loại cụ thể '{type}' trong danh mục '{material_type}'."
    else:
        target_data = data

    # --- FULL LIST MODE ---
    if mode == 'full_list':
        price_list_str = f"Bảng giá thi công chi tiết cho {type or material_type}:\n"
        for item_type, details in target_data.items():
            price_list_str += f"\n## {item_type}\n"
            for variant, price_str in details.items():
                try:
                    # Extract numeric part of price string
                    price_val = float(re.match(r'[\d,.]+', price_str.replace(',', '')).group(0))
                    price_list_str += f"- {variant}: {price_val:,.0f} VND/m²\n"
                except (ValueError, AttributeError):
                    continue # Skip if price is not a valid number
        return price_list_str.strip()

    # --- RANGE MODE (DEFAULT) ---
    all_prices = []
    for details in target_data.values():
        for price_str in details.values():
            try:
                price_val = float(re.match(r'[\d,.]+', price_str.replace(',', '')).group(0))
                all_prices.append(price_val)
            except (ValueError, AttributeError):
                continue # Skip if price is not a valid number

    if not all_prices:
        return f"Không có dữ liệu giá hợp lệ cho '{type or material_type}'."

    min_price = min(all_prices)
    max_price = max(all_prices)
    return f"Giá thi công cho {type or material_type} dao động từ {min_price:,.0f} VND/m² đến {max_price:,.0f} VND/m²."

@tool
async def search(query: str) -> str:
    """
    Search the web for information outside the system's knowledge base.
    This tool now returns a cleaner, filtered list of the top 3 results
    and handles unexpected API responses gracefully.
    """
    try:
        tavily = TavilySearch(max_results=3)
        response = await tavily.ainvoke(query)
        
        # New logic to correctly extract the list of results
        results_list = []
        if isinstance(response, dict) and 'results' in response:
            results_list = response['results']
        elif isinstance(response, list):
            results_list = response
        else:
            error_message = f"API returned an unexpected format. Expected List[Dict] or Dict containing 'results', but got {type(response)}. Content: {response}"
            print(f"Search tool error: {error_message}")
            return json.dumps([{"title": "Search API Error", "url": "", "content": error_message}])

        # Defensive check: Ensure the extracted list contains dictionaries.
        if not all(isinstance(res, dict) for res in results_list):
            error_message = f"API result list contains non-dictionary elements. Content: {results_list}"
            print(f"Search tool error: {error_message}")
            return json.dumps([{"title": "Search API Error", "url": "", "content": error_message}])

        # Filter the results to only include the keys the user requested.
        filtered_results = [
            {
                "title": res.get("title", "N/A"),
                "url": res.get("url", "N/A"),
                "content": res.get("content", "N/A")
            }
            for res in results_list
        ]
        
        return json.dumps(filtered_results, ensure_ascii=False)
    except httpx.ConnectError:
        error_msg = "Lỗi kết nối: Không thể truy cập dịch vụ tìm kiếm. Vui lòng kiểm tra kết nối mạng."
        return json.dumps([{"title": "Connection Error", "url": "", "content": error_msg}])
    except Exception as e:
        error_msg = f"Đã xảy ra lỗi không mong muốn khi tìm kiếm: {e}"
        # Also return a structured error here
        return json.dumps([{"title": "General Search Error", "url": "", "content": error_msg}])

# --- Simplified Tools ---

@tool
def run_preliminary_quote(items: List[Dict[str, Any]]) -> str:
    """Cung cấp báo giá sơ bộ (dải giá) cho một danh sách vật liệu. Dùng cho các câu hỏi giá trực tiếp, không có ngân sách."""
    return _get_preliminary_quotes(items)

@tool
async def run_market_comparison(items: List[Dict[str, Optional[str]]]) -> str:
    """So sánh giá nội bộ của DBPlus với giá thị trường chung. CHỈ dùng khi người dùng yêu cầu so sánh với 'thị trường' hoặc 'đối thủ'."""
    print(f"--- Running Tool: run_market_comparison for {len(items)} items ---")

    async def compare_item(item):
        material_type = item.get("material_type", "")
        item_type = item.get("type", "")
        
        company_price_input = {"material_type": material_type, "type": item_type, "mode": "range"}
        company_price_result = await material_price_query.ainvoke(company_price_input)
        
        search_term = item_type or material_type
        search_query = f"Giá thi công {search_term} trên thị trường"
        market_price_result = await search.ainvoke({"query": search_query})

        return f"Comparison for '{search_term}':\n- Company Price: {company_price_result}\n- Market Price: {market_price_result}"

    tasks = [compare_item(item) for item in items]
    results = await asyncio.gather(*tasks)
    return "\n\n".join(results)

@tool
def run_image_quote(image_report: str) -> str:
    """
    Phân tích báo cáo hình ảnh, báo giá mục có sẵn, cung cấp dải giá chung cho mục chỉ có vật liệu,
    và liệt kê mục không có sẵn. Đây là công cụ TOÀN DIỆN cho báo giá hình ảnh.
    """
    print("====== RUN_IMAGE_QUOTE STARTED ======")
    print(f"Raw Image Report: {image_report}")

    if not image_report or "Material:" not in image_report:
        print("ERROR: Invalid image report format")
        return "Không thể xử lý báo cáo hình ảnh. Vui lòng cung cấp hình ảnh rõ ràng hơn."
    
    in_stock_items = []
    only_material_items = []
    out_of_stock_items = []
    inferred_positions = set()
    
    line_regex = re.compile(r"Material:\s*(.+?)\s*-\s*Type:\s*(.+?)\s*-\s*Position:\s*(.+?)\s*-\s*InStock:\s*([\w_]+)")

    for line in image_report.strip().split('\n'):
        match = line_regex.match(line.strip())
        if not match:
            print(f"Line doesn't match regex: {line}")
            continue
        
        material, type_val, position, in_stock = [s.strip() for s in match.groups()]
        is_type_null = type_val.lower() in ['null', 'none', 'không xác định']

        print(f"Parsed line: material='{material}', type='{type_val}', position='{position}', in_stock='{in_stock}'")
        print(f"  is_type_null={is_type_null}")
        
        if "(phán đoán)" in position:
            inferred_positions.add(position)
        
        # Convert all keys to lowercase for more robust matching
        in_stock_lower = in_stock.lower()

        if in_stock_lower == 'true':
            item = {
                "material_type": material,
                "type": None if is_type_null else type_val
            }
            print(f"Adding to in_stock_items: {item}")
            in_stock_items.append(item)

        elif in_stock_lower == 'only_material':
            item = {
                "material": material,
                "observed_type": None if is_type_null else type_val,
                "is_type_null": is_type_null
            }
            print(f"Adding to only_material_items: {item}")
            only_material_items.append(item)

        else: # 'false' or anything else
            item_str = f"- Vật liệu '{material}' (loại: {type_val if not is_type_null else 'N/A'})"
            print(f"Adding to out_of_stock_items: {item_str}")
            out_of_stock_items.append(item_str)

    print(f"Parsed results - in_stock_items: {in_stock_items}")
    print(f"Parsed results - only_material_items: {only_material_items}")
    print(f"Parsed results - out_of_stock_items: {out_of_stock_items}")

    # --- Assemble the final response ---
    parts = []
    
    # 1. Quote for in-stock items
    if in_stock_items:
        print("Processing in-stock items for pricing...")
        parts.append("## Báo giá sơ bộ cho các vật liệu và loại cụ thể có sẵn trong kho:")
        quote_result = _get_preliminary_quotes(in_stock_items)
        parts.append(quote_result)
    
    # 2. Handle items where only the material is in stock
    if only_material_items:
        print("Processing items where only material is available...")
        notes = ["\n## Vật liệu có sẵn nhưng không có loại cụ thể:"]
        items_to_get_general_price = []
        for item in only_material_items:
            material_name = item['material']
            if item["is_type_null"]:
                notes.append(f"- Không xác định được loại cụ thể cho vật liệu '{material_name}'.")
            else:
                notes.append(f"- Chúng tôi không có loại '{item['observed_type']}' cho vật liệu '{material_name}'.")
            items_to_get_general_price.append({"material_type": material_name, "type": None})
        
        # Remove duplicates before getting the general price range
        unique_items_to_price = [dict(t) for t in {tuple(d.items()) for d in items_to_get_general_price}]
        if unique_items_to_price:
            notes.append("\nDưới đây là dải giá chung cho các loại vật liệu đó:")
            quote_result = _get_preliminary_quotes(unique_items_to_price)
            notes.append(quote_result)
        
        parts.append("\n".join(notes))

    # 3. List completely out-of-stock items
    if out_of_stock_items:
        parts.append("\n## Vật liệu không có trong danh mục:")
        parts.append("\n".join(out_of_stock_items))

    # 4. Add inference note
    if inferred_positions:
        parts.append("\n**Ghi chú:** Một số vị trí được ước tính dựa trên phán đoán từ hình ảnh.")
        
    # 5. Add call-to-action for detailed quote
    parts.append("\n## Yêu cầu báo giá chi tiết")
    parts.append("Để nhận báo giá chi tiết và tư vấn lựa chọn vật liệu phù hợp với nhu cầu, vui lòng cung cấp:")
    parts.append("1. **Diện tích cần thi công (m²)** - ví dụ: 30m²")
    parts.append("2. **Ngân sách dự kiến (VND)** - ví dụ: 50,000,000 VND")
        
    if not in_stock_items and not only_material_items and not out_of_stock_items:
        print("WARNING: No materials recognized from image report")
        return "Không thể nhận diện hoặc phân loại bất kỳ vật liệu nào từ báo cáo hình ảnh. Vui lòng cung cấp hình ảnh rõ ràng hơn."

    final_response = "\n".join(parts)
    print("====== RUN_IMAGE_QUOTE COMPLETED ======")
    return final_response


@tool
async def run_detailed_quote(items: List[Dict[str, Optional[str]]], area: str, budget: float) -> str:
    """Tìm 1-2 lựa chọn TỐI ƯU NHẤT cho MỘT loại vật liệu dựa trên ngân sách và diện tích. Dùng khi người dùng muốn có đề xuất cụ thể."""
    print(f"--- Running Tool: run_detailed_quote ---")
    print(f"Input - Items: {items}, Area: {area}, Budget: {budget}")
    
    try:
        normalized_area = _parse_area(area)
        if normalized_area <= 0:
            return "**Lỗi:** Diện tích phải là một số dương. Vui lòng cung cấp diện tích hợp lệ."
    except ValueError as e:
        return f"**Lỗi xử lý diện tích:** {e}. Vui lòng cung cấp diện tích hợp lệ, ví dụ: '30m2' hoặc '50 mét vuông'."

    if not items or not isinstance(items, list) or len(items) == 0:
        return "**Lỗi:** Vui lòng cung cấp ít nhất một loại vật liệu để báo giá chi tiết."

    # Process each item and collect results
    all_results = []
    total_budget_used = 0

    for item in items:
        material_type = item.get("material_type")
        specific_type = item.get("type")
    
        if not material_type:
            all_results.append(f"**Lỗi:** Một vật liệu trong danh sách không có thông tin 'material_type'.")
            pass

        print(f"Processing material: {material_type}, type: {specific_type}")
    
    full_list_input = {"material_type": material_type, "type": specific_type, "mode": "full_list"}
    try:
        full_list_result = await material_price_query.ainvoke(full_list_input)
        all_variants = _parse_full_price_list(full_list_result)

        if not all_variants:
            all_results.append(f"**Không tìm thấy thông tin giá chi tiết cho** '{specific_type or material_type}'.")
        else:
            # Calculate per-item budget based on number of items
            item_budget = budget / len(items)
            budget_per_sqm = item_budget / normalized_area

            valid_options = [v for v in all_variants if v["price"] <= budget_per_sqm]

            if not valid_options:
                min_price = min(v['price'] for v in all_variants)
                all_results.append(
                    f"**Ngân sách không đủ cho** '{specific_type or material_type}'.\n"
                    f"- Ngân sách cho vật liệu này: {item_budget:,.0f} VND ({budget_per_sqm:,.0f} VND/m²)\n"
                    f"- Lựa chọn rẻ nhất có giá: {min_price:,.0f} VND/m²"
                )
            else:
                # Find the best option (most expensive within budget)
                best_option = max(valid_options, key=lambda x: x["price"])
                final_price_per_sqm = best_option["price"]
                total_cost = final_price_per_sqm * normalized_area
                total_budget_used += total_cost

                # Format the result in markdown table
                result = (
                    f"### Báo giá chi tiết cho {material_type} {specific_type or ''}\n"
                    f"| Hạng mục | Loại cụ thể | Diện tích | Đơn giá | Thành tiền |\n"
                    f"|---|---|---|---|---|\n"
                    f"| {material_type} | {best_option['variant']} | {normalized_area} m² | {final_price_per_sqm:,.0f} VND/m² | {total_cost:,.0f} VND |"
                )
                all_results.append(result)

    except Exception as e:
        all_results.append(f"**Lỗi xử lý** '{material_type}': {str(e)}")


    # Combine all results
    if not all_results:
        return "**Lỗi:** Không thể tạo báo giá chi tiết với thông tin được cung cấp."

    final_response = "\n\n".join(all_results)

    # Add summary if we have valid quotes
    if total_budget_used > 0:
        budget_status = "trong ngân sách" if total_budget_used <= budget else "**vượt ngân sách**"
        final_response += f"\n\n### Tổng chi phí ước tính: {total_budget_used:,.0f} VND ({budget_status})"

        # Add recommendations if over budget
        if total_budget_used > budget:
            final_response += f"\n\n**Khuyến nghị:** Ngân sách {budget:,.0f} VND không đủ cho các lựa chọn trên. Bạn có thể:\n"
            final_response += "1. Tăng ngân sách\n"
            final_response += "2. Giảm diện tích\n"
            final_response += "3. Chọn vật liệu có giá thành thấp hơn"

    return final_response


async def _get_all_variants_for_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Helper to get all variants and prices for a single material item."""
    material_type = item.get("material_type")
    item_type = item.get("type") # This can be None
    
    # This uses the rewritten material_price_query logic
    full_list_input = {"material_type": material_type, "type": item_type, "mode": "full_list"}
    full_list_result = await material_price_query.ainvoke(full_list_input)
    
    # _parse_full_price_list returns a list of {"variant": name, "price": 123.0}
    all_variants = _parse_full_price_list(full_list_result)
    
    # Add area to each variant for later calculation
    try:
        area = _parse_area(item.get("area", "0"))
        for v in all_variants:
            v['area'] = area
            # For identification in the final result, include the specific type if it was provided
            v['material'] = f"{material_type} ({item_type or v.get('parent_type', 'N/A')})"
    except ValueError:
        return [] # Skip item if area is invalid
        
    return all_variants

@tool
async def find_optimal_combination_quote(items: List[Dict[str, Any]], total_budget: float) -> str:
    """Tìm sự kết hợp TỐI ƯU cho NHIỀU loại vật liệu dưới một ngân sách TỔNG. Dùng cho các dự án phức tạp có nhiều hạng mục."""
    print(f"--- Running Tool: find_optimal_combination_quote for {len(items)} items ---")
    
    # 1. Get all possible variants for each item
    tasks = [_get_all_variants_for_item(item) for item in items]
    variants_per_item = await asyncio.gather(*tasks)

    if not all(variants_per_item):
        return "Lỗi: Không thể lấy danh sách vật liệu cho một hoặc nhiều hạng mục. Vui lòng kiểm tra lại loại vật liệu và loại."

    # 2. Generate all combinations (Cartesian product)
    all_combinations = list(itertools.product(*variants_per_item))

    # 3. Calculate cost for each combination and find valid ones
    valid_combinations = []
    for combo in all_combinations:
        total_cost = sum(variant['price'] * variant['area'] for variant in combo)
        if total_cost <= total_budget:
            valid_combinations.append({'combo': combo, 'total_cost': total_cost})

    if not valid_combinations:
        return (f"Rất tiếc, không có sự kết hợp vật liệu nào phù hợp với tổng ngân sách {total_budget:,.0f} VND. "
                "Vui lòng cân nhắc tăng ngân sách hoặc thay đổi vật liệu.")

    # 4. Find the best combination (closest to the budget)
    best_combination = max(valid_combinations, key=lambda x: x['total_cost'])

    # 5. Format the response
    response_lines = [
        f"Đề xuất tối ưu nhất cho ngân sách {total_budget:,.0f} VND:",
        "---"
    ]
    for variant_details in best_combination['combo']:
        item_cost = variant_details['price'] * variant_details['area']
        response_lines.append(
            f"- Hạng mục: **{variant_details['material']}**\n"
            f"  - Lựa chọn: {variant_details['variant']}\n"
            f"  - Diện tích: {variant_details['area']} m²\n"
            f"  - Đơn giá: {variant_details['price']:,.0f} VND/m²\n"
            f"  - Chi phí: {item_cost:,.0f} VND"
        )
    
    response_lines.append("---")
    response_lines.append(f"**Tổng chi phí ước tính: {best_combination['total_cost']:,.0f} VND**")
    
    return "\n".join(response_lines)


@tool
async def find_material_options(material_type: str, budget: float, area: str, type: Optional[str] = None) -> str:
    """
    Find all material options that fit within a budget constraint.

    Args:
        material_type: Category of material (e.g., 'gỗ', 'đá', 'sơn')
        budget: Total budget (VND)
        area: Area (e.g., "25m2")
        type: Specific type (optional)

    Returns:
        List of options that fit within the budget

    Use only when the user wants to explore ALL OPTIONS for ONE specific material type based on budget constraints.
    """
    print(f"--- Running Tool: find_material_options ---")
    try:
        normalized_area = _parse_area(area)
        if normalized_area <= 0:
            return "Lỗi: Diện tích phải là một số dương."
    except ValueError as e:
        return f"Lỗi xử lý diện tích: {e}. Vui lòng cung cấp diện tích hợp lệ."

    full_list_input = {"material_type": material_type, "type": type, "mode": "full_list"}
    full_list_result = await material_price_query.ainvoke(full_list_input)

    all_variants = _parse_full_price_list(full_list_result)
    if not all_variants:
        return f"Không tìm thấy danh sách giá chi tiết cho '{type or material_type}'."

    budget_per_sqm = budget / normalized_area
    valid_options = [v for v in all_variants if v["price"] <= budget_per_sqm]

    if not valid_options:
        min_price = min(v['price'] for v in all_variants) if all_variants else 0
        return (f"Rất tiếc, không có lựa chọn vật liệu nào cho '{type or material_type}' phù hợp với ngân sách "
                f"{budget:,.0f} VND cho diện tích {normalized_area} m².\n"
                f"Ngân sách của bạn tương đương {budget_per_sqm:,.0f} VND/m², trong khi lựa chọn rẻ nhất có giá "
                f"{min_price:,.0f} VND/m².")

    response = (f"Dựa trên ngân sách {budget:,.0f} VND cho {normalized_area} m² (~{budget_per_sqm:,.0f} VND/m²), "
                f"đây là các lựa chọn dành cho bạn:\n")
    
    for option in sorted(valid_options, key=lambda x: x['price']):
        total_cost = option['price'] * normalized_area
        # Display format changes based on whether a specific type was requested
        if type: # User already knows the type, just show the variant
            display_name = option['variant']
        else: # User asked for a broad category, so show the full type + variant
            display_name = f"{option['parent_type']} - {option['variant']}"

        response += (f"- **{display_name}**:\n"
                     f"  - Đơn giá: {option['price']:,.0f} VND/m²\n"
                     f"  - Tổng chi phí ước tính: {total_cost:,.0f} VND\n")

    return response.strip()


@tool
def save_quote(project_name: str, quote_details: str) -> str:
    """
    Save a quote with a specific project name for later reference.

    Args:
        project_name: Project name (letters, numbers, and hyphens only)
        quote_details: Quote content to save

    Returns:
        Message confirming the quote has been saved

    Use when the user wants to save a quote with a specific name (different from the save_quote parameter in quote_materials).
    """
    if not re.match(r'^[a-zA-Z0-9_-]+$', project_name):
        return "Lỗi: Tên dự án chỉ được chứa chữ cái, số, gạch dưới (_) và gạch nối (-)."
    
    filename = os.path.join(QUOTES_DIR, f"{project_name}.txt")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    content_to_save = f"Quote saved on: {timestamp}\n\n{quote_details}"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content_to_save)
        
    return f"Báo giá đã được lưu thành công với tên '{project_name}'."

@tool
def get_saved_quotes(project_name: Optional[str] = None) -> str:
    """
    Retrieve previously saved quotes.

    Args:
        project_name: Specific project name to retrieve (optional)

    Returns:
        List of saved quotes or specific quote content

    Use when the user wants to view previously saved quotes.
    """
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

def _distribute_and_enrich_areas(components: List[Dict[str, Any]], area_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Updates components from the image report with details from the user-provided area_map.
    The area_map keys are positions (e.g., "sàn", "tường").
    """
    enriched_components = []

    # Create a lookup for faster access
    component_map = {c.get("position"): c for c in components}

    for position, details in area_map.items():
        # Check if this position is a group (e.g., "tường")
        is_group, group_key = _is_position_group(position)

        if is_group:
            # Find all components belonging to this group (e.g., all walls)
            group_components = [
                comp for pos, comp in component_map.items()
                if pos and any(pos.startswith(prefix) for prefix in POSITION_GROUP_MAP.get(group_key, []))
            ]

            if not group_components:
                continue

            # Distribute area if provided
            total_area_str = details.get("area")
            if total_area_str:
                try:
                    total_area = parse_area(total_area_str)
                    area_per_component = total_area / len(group_components)
                    print(f"Distributing {total_area}m² over {len(group_components)} '{group_key}' components -> {area_per_component:.2f}m² each.")
                    for comp in group_components:
                        comp['area'] = f"{area_per_component:.2f}m2"
                except (ValueError, ZeroDivisionError) as e:
                    print(f"Could not distribute area for group '{group_key}': {e}")

            # Update material and type for all in the group
            for comp in group_components:
                comp['material_type'] = details.get('material_type', comp.get('material_type'))
                comp['type'] = details.get('type', comp.get('type')) # Use existing type if not provided

            enriched_components.extend(group_components)

        else: # It's a specific position
            if position in component_map:
                comp = component_map[position]
                comp.update(details) # Update component with all details from area_map
                enriched_components.append(comp)

    # Ensure no duplicates if a component was part of a group and also specified individually
    final_components = list({v['position']: v for v in enriched_components}.values())

    # Add back any components from the original report that were not in the area_map
    for comp in components:
        if comp.get('position') not in {c.get('position') for c in final_components}:
            final_components.append(comp)

    return final_components

def _is_position_group(position: str) -> (bool, Optional[str]):
    """Checks if a position string corresponds to a defined group."""
    for group, prefixes in POSITION_GROUP_MAP.items():
        # Use exact match for the group key to avoid matching substrings
        # e.g., "tường trái" should not match the group "tường".
        if position.lower() in prefixes:
            return True, group
    return False, None

def _parse_dimensions_and_calculate_wall_area(dim_str: str) -> float:
    """Parses a dimension string 'LxWxH' and calculates the area of 4 walls."""
    parts = re.findall(r'(\d+\.?\d*)', dim_str)
    if len(parts) < 3:
        raise ValueError(f"Invalid dimension string '{dim_str}'. Expected 3 numbers for L, W, H.")
    l, w, h = map(float, parts[:3])
    return ((l + w) * 2) * h

def _enrich_components_from_area_map(base_components: List[Dict], area_map: Dict) -> Tuple[List[Dict], List[str]]:
    """
    The main logic hub. Uses area_map as the source of truth to build a new component list.
    It enriches this list with data from the base_components (from image).
    It also reports on items seen in the image but not included in the user's area_map.
    """
    quoted_components = []
    notes = []

    # Create a lookup from the base components for easy data retrieval
    base_comp_map = {c.get("position", "").lower(): c for c in base_components if c.get("position")}

    # The area_map keys are the items the user *wants* quoted.
    for position, details in area_map.items():
        pos_lower = position.lower()

        # Handle room dimensions as a special case
        if 'dimensions' in details:
            try:
                wall_area = _parse_dimensions_and_calculate_wall_area(details['dimensions'])
                # Create a component for the walls
                wall_comp = {
                    "position": "Tường (từ phòng)",
                    "area": str(wall_area),
                    "material_type": details.get("material_type"),
                    "type": details.get("type")
                }
                # If there are other wall components from image, this will override them
                # A more complex logic could merge them. For now, this is explicit.
                quoted_components.append(wall_comp)
                continue # Move to the next item in area_map
            except ValueError as e:
                notes.append(f"Lưu ý: Không thể tính diện tích từ kích thước phòng '{details['dimensions']}': {e}")
                continue

        # Start with user-provided details
        new_comp = details.copy()
        new_comp["position"] = position # Ensure position is set

        # If this position was also in the image, pull its data to fill gaps
        if pos_lower in base_comp_map:
            image_comp = base_comp_map[pos_lower]
            # User's spec overrides image analysis
            new_comp.setdefault("material_type", image_comp.get("material_type"))
            new_comp.setdefault("type", image_comp.get("type"))

        # Ensure essential keys exist
        if "material_type" not in new_comp or "area" not in new_comp:
            notes.append(f"Lưu ý: Hạng mục '{position}' bị thiếu 'material_type' hoặc 'area' và đã được bỏ qua.")
            continue

        quoted_components.append(new_comp)

    # Now, find what was in the image but NOT in the user's explicit area_map
    area_map_positions = {k.lower() for k in area_map.keys()}
    missing_positions = sorted(list(base_comp_map.keys() - area_map_positions))

    if missing_positions:
        missing_str = ", ".join(f"'{pos.title()}'" for pos in missing_positions)
        notes.append(f"Ghi chú: Các hạng mục sau được thấy trong ảnh nhưng không được yêu cầu báo giá: {missing_str}.")

    return quoted_components, notes

def _get_price_range(material_type: str, specific_type: Optional[str] = None) -> str:
    """
    Helper to get a simple price range string, with case-insensitive type matching.
    """
    data = _load_json_data(material_type)
    if not data:
        return f"Không có dữ liệu cho '{material_type}'"

    try:
        prices = []
        target_data = None
        
        # Case-insensitive lookup for the specific type
        if specific_type:
            for key, value in data.items():
                if key.lower() == specific_type.lower():
                    target_data = value
                    break
        else:
            target_data = data # Use all types

        if target_data:
            if specific_type and isinstance(target_data, dict):
                # Get prices from a specific type's variants
                prices.extend(target_data.values())
            elif not specific_type and isinstance(target_data, dict):
                # Get prices from all types
                for type_data in target_data.values():
                    if isinstance(type_data, dict):
                        prices.extend(type_data.values())
        
        if prices:
            numeric_prices = []
            for p_str in prices:
                match = re.search(r'([\d,.]+)', str(p_str).replace(',', ''))
                if match:
                    numeric_prices.append(float(match.group(1)))
            
            if numeric_prices:
                min_price = min(numeric_prices)
                max_price = max(numeric_prices)
                type_name = specific_type or material_type
                return f"Giá cho {type_name} dao động từ {min_price:,.0f} - {max_price:,.0f} VND/m²"
    
    except Exception as e:
        return f"Lỗi khi xử lý giá cho '{material_type}': {e}"

    # Fallback message
    return f"Không tìm thấy thông tin giá cho '{specific_type or material_type}'"

def _create_params_summary(mode: str, **kwargs) -> str:
    """Creates a formatted string of the parameters used for the quote."""
    summary_lines = ["[Quote Parameters Used]:", f"- Mode: {mode}"]
    for key, value in kwargs.items():
        if value:
            if key == 'area_map' and isinstance(value, dict):
                summary_lines.append("- Area Map:")
                for mat, details in value.items():
                    summary_lines.append(f"  - {mat}: {details}")
            else:
                summary_lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    return "\n".join(summary_lines)

@tool
def save_quote_to_file(project_name: str, content: str) -> str:
    """Saves a quote to a file with a given project name."""
    try:
        filename = os.path.join(QUOTES_DIR, f"{project_name}.txt")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Quote successfully saved as '{project_name}.txt'"
    except Exception as e:
        return f"Error saving quote: {e}"

@tool
async def compare_market_prices(
    material_list: Optional[List[Dict[str, Any]]] = None,
    image_report: Optional[Any] = None
) -> str:
    """
    Compares DBPlus prices with market prices for a list of materials or materials from an image report.
    This tool deduplicates materials and returns the top search result for each unique material type.
    Use this tool when the user explicitly asks to "compare" prices.
    
    Args:
        material_list: A specific list of materials to compare. Each dict should have 'material_type' and optionally 'type'.
        image_report: An image analysis report (string) or a pre-parsed list of components.
    
    Returns:
        A detailed string with DBPlus prices and a single, most relevant market search result for each unique material.
    """
    print("\n--- TOOL: compare_market_prices ---")
    
    components_to_compare = []
    if image_report:
        print("Mode: Comparing materials from image report.")
        if isinstance(image_report, str):
            components_to_compare = parse_image_report(image_report)
        elif isinstance(image_report, list):
            for item in image_report:
                if 'material' in item and 'material_type' not in item:
                    item['material_type'] = item.pop('material')
            components_to_compare = image_report
        else:
             return "Lỗi: Định dạng 'image_report' không hợp lệ. Phải là chuỗi báo cáo hoặc danh sách các hạng mục."

    elif material_list:
        print(f"Mode: Comparing materials from provided list: {material_list}")
        for item in material_list:
            if 'material' in item and 'material_type' not in item:
                item['material_type'] = item.pop('material')
        components_to_compare = material_list
    else:
        return "Lỗi: Vui lòng cung cấp một danh sách vật liệu hoặc báo cáo hình ảnh để so sánh giá."

    if not components_to_compare:
        return "Lỗi: Không tìm thấy vật liệu hợp lệ để so sánh."

    # --- Deduplication Logic ---
    unique_materials_to_query = []
    seen_combinations = set()
    for item in components_to_compare:
        # Use a tuple of (material_type, type) to identify unique items
        material_type = item.get("material_type")
        specific_type = item.get("type")
        combination = (material_type, specific_type)
        if combination not in seen_combinations:
            seen_combinations.add(combination)
            unique_materials_to_query.append(item)
    
    print(f"Found {len(unique_materials_to_query)} unique materials to compare.")

    async def get_comparison_for_item(item: Dict[str, Any]) -> str:
        material_type = item.get("material_type")
        specific_type = item.get("type")
        if not material_type:
            return ""

        dbplus_price_str = _get_price_range(material_type, specific_type)
        search_term = f"{specific_type} {material_type}" if specific_type else material_type
        search_query = f"Giá thi công {search_term} tại Việt Nam"
        
        market_price_info_json = "[]" # Default to an empty JSON array string
        try:
            # The search tool now returns a clean JSON string of a list of dicts.
            market_search_result_str = await search.ainvoke(search_query)
            
            # We don't need to do much processing here. The search tool already returns
            # the format we need. We just pass this JSON string along.
            # Basic validation to ensure it's a list.
            parsed_results = json.loads(market_search_result_str)
            if isinstance(parsed_results, list):
                market_price_info_json = market_search_result_str
            else:
                 market_price_info_json = json.dumps([{"title": "Search Error", "url": "", "content": "API returned non-list data."}])

        except json.JSONDecodeError:
            market_price_info_json = json.dumps([{"title": "Search Error", "url": "", "content": "Failed to parse search results."}])
        except Exception as e:
            market_price_info_json = json.dumps([{"title": "Search Error", "url": "", "content": f"An unexpected error occurred: {e}"}])

        # The final output for this item is a structured string that the RESPONSE_PROMPT will parse.
        # It clearly separates the company price from the raw market data JSON.
        return (
            f"### Hạng mục: {search_term.title()}\n"
            f"- **Giá DBPlus**: {dbplus_price_str}\n"
            f"- **Dữ liệu giá thị trường (thô)**:\n```json\n{market_price_info_json}\n```\n"
        )

    tasks = [get_comparison_for_item(item) for item in unique_materials_to_query]
    results = await asyncio.gather(*tasks)
    
    valid_results = [res for res in results if res]
    if not valid_results:
        return "Không thể lấy thông tin giá cho các vật liệu được yêu cầu."
        
    final_report = "## Kết quả so sánh giá:\n\n" + "\n\n".join(valid_results)
    final_report += "\n\n*Ghi chú: Người trả lời cuối cùng có trách nhiệm tóm tắt dữ liệu thô ở trên thành một bảng so sánh rõ ràng cho người dùng.*"
    
    return final_report

def _save_material_quote(material_type, type, area, budget, options, result):
    """Helper to save a material quote."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    quote_data = {
        "timestamp": timestamp,
        "material_type": material_type,
        "type": type,
        "area": area,
        "budget": budget,
        "options": options,
        "result": result
    }

    try:
        os.makedirs(QUOTES_DIR, exist_ok=True)
        quote_file = os.path.join(QUOTES_DIR, f"quote_{material_type}_{timestamp}.json")
        with open(quote_file, "w", encoding="utf-8") as f:
            json.dump(quote_data, f, ensure_ascii=False, indent=2)
        return f"_Quote saved (ID: quote_{material_type}_{timestamp})_"
    except Exception as e:
        print(f"ERROR saving quote: {e}")
        return f"_Error saving quote: {e}_"

def _get_filename_for_material(material_type: str) -> Optional[str]:
    """Helper function to get the filename for a material type."""
    material_map = {
        'sơn': 'paint.json',
        'gỗ': 'wood.json',
        'đá': 'stone.json',
        'giấy dán tường': 'wallpaper.json',
        'gạch': 'tile.json'
    }
    lookup_key = material_type.lower()

    if lookup_key not in material_map:
        return None

    return os.path.join(_data_dir, material_map[lookup_key])

# --- Unified Tools List ---

TOOLS = {
    "quote_materials": quote_materials,
    "get_saved_quotes": get_saved_quotes,
    "search": search,
    "compare_market_prices": compare_market_prices,
    "save_quote_to_file": save_quote_to_file,
}

def execute_tool(tool_name: str, args: dict) -> str:
    """Thực thi một công cụ dựa trên tên và các tham số.
    
    Args:
        tool_name: Tên của công cụ cần gọi
        args: Các tham số đầu vào cho công cụ
        
    Returns:
        Kết quả trả về dạng chuỗi từ việc gọi công cụ
    """
    print(f"Executing tool {tool_name} with args: {args}")
    
    try:
        # Tìm công cụ theo tên
        if tool_name == "quote_materials":
            # Truyền args trực tiếp vào invoke() - BaseTool.invoke() chấp nhận dict làm đầu vào
            result = quote_materials.invoke(args)
            return result
            
        elif tool_name == "get_saved_quotes":
            result = get_saved_quotes.invoke(args)
            return result
            
        elif tool_name == "search":
            # Đối với hàm bất đồng bộ
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(search.ainvoke(args))
            finally:
                loop.close()
            return result
            
        elif tool_name == "compare_market_prices":
            # Đối với hàm bất đồng bộ
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(compare_market_prices.ainvoke(args))
            finally:
                loop.close()
            return result
            
        elif tool_name == "save_quote_to_file":
            result = save_quote_to_file.invoke(args)
            return result
            
        else:
            return f"Tool {tool_name} is not supported in execute_tool function."
            
    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        print(f"Error executing tool {tool_name}: {str(e)}")
        print(f"Traceback: {traceback_str}")
        
        # BACKUP PLAN: Nếu mọi thứ thất bại, trả về lỗi dễ đọc
        if tool_name == "quote_materials":
            return (f"Không thể tạo báo giá chi tiết do lỗi kỹ thuật.\n"
                   f"Vui lòng thử lại với mô tả rõ ràng hơn về vật liệu, diện tích và/hoặc ngân sách.")
        else:
            return f"Lỗi khi thực hiện {tool_name}: {str(e)}"
