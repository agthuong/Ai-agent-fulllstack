"""New tools for the AI interior design quotation system using the DatabaseNoiThat.json structure."""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults

from .database_utils import (
    get_all_categories,
    get_material_types,
    get_material_subtypes,
    get_material_variants,
    get_material_price,
    search_materials,
    get_price_range
)
from .tools_quotes import calculate_from_area_map, parse_area

# Load the database once at module level
_current_dir = os.path.dirname(os.path.abspath(__file__))
_data_dir = os.path.join(_current_dir, '..', '..', 'data')
_database_path = os.path.join(_data_dir, 'DatabaseNoiThat.json')

with open(_database_path, 'r', encoding='utf-8') as f:
    DATABASE = json.load(f)

# --- Path setup for data files ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
_data_dir = os.path.join(_current_dir, '..', '..', 'data')

# Create directory to save quotes if it doesn't exist
QUOTES_DIR = "saved_quotes"
os.makedirs(QUOTES_DIR, exist_ok=True)

@tool
def get_internal_price_new(category: str, material_type: str, subtype: str, variant: Optional[str] = None, cost_type: str = "combined") -> str:
    """
    (Giá nội bộ) Tra cứu giá của một vật liệu cụ thể từ cơ sở dữ liệu mới của công ty.
    Sử dụng khi người dùng hỏi giá trực tiếp cho một sản phẩm.

    Args:
        category: Danh mục (ví dụ: 'Sàn', 'Tường và vách')
        material_type: Loại vật liệu (ví dụ: 'Sàn gạch', 'Giấy dán tường')
        subtype: Phân loại (ví dụ: 'Gạch cao cấp', 'Giấy dán tường Đạt Minh')
        variant: Biến thể cụ thể (ví dụ: 'Gạch 600x1200mm'). Nếu không có, trả về khoảng giá.
        cost_type: Loại chi phí - 'material' (vật tư), 'labor' (nhân công), hoặc 'combined' (tổng hợp)
    """
    if variant:
        # Get specific variant price
        price = get_material_price(category, material_type, subtype, variant, cost_type)
        if price is not None:
            cost_type_vn = {
                "material": "vật tư",
                "labor": "nhân công",
                "combined": "tổng hợp"
            }.get(cost_type, "tổng hợp")
            
            return f"Giá {cost_type_vn} cho {variant} ({subtype}, {material_type}, {category}) là {price:,.0f} VND/m²."
        else:
            return f"Không tìm thấy giá cho {variant} ({subtype}, {material_type}, {category})."
    else:
        # Get price range for subtype
        min_price, max_price = get_price_range(category, material_type, subtype, cost_type)
        if min_price is not None and max_price is not None:
            cost_type_vn = {
                "material": "vật tư",
                "labor": "nhân công",
                "combined": "tổng hợp"
            }.get(cost_type, "tổng hợp")
            
            return f"Giá {cost_type_vn} cho {subtype} ({material_type}, {category}) dao động từ {min_price:,.0f} VND/m² đến {max_price:,.0f} VND/m²."
        else:
            return f"Không tìm thấy dữ liệu giá cho {subtype} ({material_type}, {category})."

@tool
def search_materials_new(query: str) -> str:
    """
    (Tìm kiếm vật liệu) Tìm kiếm vật liệu theo tên trong cơ sở dữ liệu mới.
    Sử dụng khi người dùng hỏi về một vật liệu nhưng không rõ danh mục cụ thể.

    Args:
        query: Từ khóa tìm kiếm
    """
    results = search_materials(query)
    
    if not results:
        return f"Không tìm thấy vật liệu nào phù hợp với '{query}'."
    
    # Format results
    formatted_results = []
    for item in results[:10]:  # Limit to 10 results
        material_cost_str = f"{item['material_cost']:,.0f}" if item['material_cost'] is not None else "N/A"
        labor_cost_str = f"{item['labor_cost']:,.0f}" if item['labor_cost'] is not None else "N/A"
        combined_cost_str = f"{item['combined_cost']:,.0f}" if item['combined_cost'] is not None else "N/A"
        
        formatted_results.append(
            f"- {item['variant']} ({item['subtype']}, {item['material_type']}, {item['category']})\n"
            f"  + Vật tư: {material_cost_str} VND/m²\n"
            f"  + Nhân công: {labor_cost_str} VND/m²\n"
            f"  + Tổng: {combined_cost_str} VND/m²"
        )
    
    return f"Tìm thấy {len(results)} kết quả cho '{query}':\n\n" + "\n\n".join(formatted_results)

@tool
def get_categories_new() -> str:
    """(Danh mục) Lấy danh sách tất cả các danh mục vật liệu có sẵn trong cơ sở dữ liệu mới."""
    categories = get_all_categories()
    return "Các danh mục vật liệu có sẵn:\n- " + "\n- ".join(categories)

@tool
def get_material_types_new(category: str) -> str:
    """
    (Loại vật liệu) Lấy danh sách các loại vật liệu trong một danh mục cụ thể.

    Args:
        category: Danh mục (ví dụ: 'Sàn', 'Tường và vách')
    """
    material_types = get_material_types(category)
    if not material_types:
        return f"Không tìm thấy loại vật liệu nào trong danh mục '{category}'."
    
    return f"Các loại vật liệu trong danh mục '{category}':\n- " + "\n- ".join(material_types)

@tool
def get_material_subtypes_new(category: str, material_type: str) -> str:
    """
    (Phân loại vật liệu) Lấy danh sách các phân loại trong một loại vật liệu cụ thể.

    Args:
        category: Danh mục (ví dụ: 'Sàn')
        material_type: Loại vật liệu (ví dụ: 'Sàn gạch')
    """
    subtypes = get_material_subtypes(category, material_type)
    if not subtypes:
        return f"Không tìm thấy phân loại nào trong '{material_type}' ({category})."
    
    return f"Các phân loại trong '{material_type}' ({category}):\n- " + "\n- ".join(subtypes)

@tool
def get_market_price_new(material: str) -> List[Dict[str, str]]:
    """(Giá thị trường) Tìm kiếm giá thị trường của một vật liệu bằng Tavily Search API."""
    print(f"--- INFO: Searching market price for '{material}' via Tavily ---")
    try:
        search_tool = TavilySearchResults(max_results=3)
        query = f"giá thị trường hiện tại của {material} ở Việt Nam"
        raw_results = search_tool.invoke(query)
        
        # Simplify the results
        simplified_results = []
        if isinstance(raw_results, list):
            for res in raw_results:
                if isinstance(res, dict):
                    simplified_results.append({
                        "title": res.get("title", "N/A"),
                        "url": res.get("url", "N/A"),
                        "content": res.get("content", "N/A")
                    })
        
        return simplified_results
    except Exception as e:
        print(f"Error during Tavily search: {e}")
        # Return an error structure that is also a list of dicts
        return [{"error": f"Lỗi khi tìm kiếm giá thị trường qua Tavily: {e}"}]

# --- Tools for Memory/Quote Management ---

@tool
def get_saved_quotes_new(project_name: Optional[str] = None) -> str:
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
def save_quote_to_file_new(project_name: str, content: str) -> str:
    """(Nội bộ) Lưu một báo giá vào file với tên dự án được chỉ định."""
    try:
        filename = os.path.join(QUOTES_DIR, f"{project_name}.txt")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Đã lưu báo giá với tên '{project_name}'."
    except Exception as e:
        return f"Lỗi khi lưu báo giá: {e}"

@tool
def generate_quote_from_image(image_report: str, area_map: dict = None) -> str:
    """
    (Phân tích ảnh) Phân tích báo cáo hình ảnh và tạo báo giá sơ bộ.
    Sử dụng khi người dùng cung cấp hình ảnh.

    Args:
        image_report: Báo cáo phân tích hình ảnh
        area_map: Bản đồ diện tích đã được phân tích (nếu có)
    """
    print(f"--- INFO: Generating quote from image report ---")
    try:
        # Use provided area_map or parse from image_report if not provided
        if area_map is None:
            area_map = _parse_image_report_to_area_map(image_report)
        
        # Calculate costs using the area map with fallback for partial paths
        result = _calculate_from_area_map_with_fallback(DATABASE, area_map)
        
        # Format the result as a markdown table
        formatted_result = _format_quote_result(result)
        
        return formatted_result
    except Exception as e:
        return f"Lỗi khi tạo báo giá từ hình ảnh: {e}"

def _parse_image_report_to_area_map(image_report: str) -> dict:
    """
    Parse image report into an area map structure.

    The report is expected in the new, structured JSON format from the Vision model.
    This function translates the JSON report into a dictionary of surfaces,
    each with a path to the material in the database.
    """
    import json
    from .room_parser import create_area_map_from_room_size
    
    surfaces = {}
    
    # Check if the input is a room size (e.g., "5x10x6")
    if isinstance(image_report, str) and "x" in image_report and len(image_report.split("x")) == 3:
        try:
            # Try to parse as room dimensions
            return create_area_map_from_room_size(image_report)
        except ValueError:
            # Not a valid room size format, continue with normal parsing
            pass
    
    try:
        # The vision model is instructed to return a valid JSON array string.
        # Handle case where image_report might contain '[Image Analysis Report]:' prefix
        clean_image_report = image_report
        if image_report.startswith('[Image Analysis Report]:'):
            clean_image_report = image_report.split(':', 1)[1].strip()
        
        report_data = json.loads(clean_image_report)
        
        for item in report_data:
            position = item.get("position", "unknown").strip()
            category = item.get("category")
            material_type = item.get("material_type")
            subtype = item.get("subtype")
            in_stock = item.get("in_stock", "false").strip()

            # Process only items that are available in our catalog.
            if in_stock == 'true' or in_stock == 'only_material':
                # Build the database path directly from the structured JSON data.
                # We'll build a flexible path that can match varying database structures
                path = []
                if category:
                    path.append(category)
                # If in_stock is 'only_material', set material_type to None as it's not in our catalog
                if in_stock == 'only_material':
                    material_type = None
                if material_type and material_type != 'null':
                    path.append(material_type)
                if subtype and subtype != 'null':
                    path.append(subtype)
                
                # A valid path must have at least a category and a material type.
                if len(path) >= 2:
                    surface_info = {
                        "path": path
                    }
                    # Only include area if it's explicitly provided in the image report
                    # If no area is provided, we'll show unit prices only
                    if "area" in item and item["area"] is not None:
                        surface_info["area"] = item["area"]
                    surfaces[position] = surface_info
    except (json.JSONDecodeError, TypeError):
        # If the report is not valid JSON, we cannot parse it.
        # This might happen if the vision model fails to follow instructions.
        # We will return an empty map and the error will be handled upstream.
        pass

    return {"surfaces": surfaces}

def _calculate_from_area_map_with_fallback(data, area_map):
    """
    Calculate costs from area map with fallback to price ranges for partial paths.
    
    This function handles cases where the vision model provides incomplete paths
    (e.g., only category and material_type) by falling back to price range calculations.
    """
    from .database_utils import get_price_range
    from .tools_quotes import calculate_from_area_map, resolve_path, parse_area
    
    # First try the standard calculation
    result = calculate_from_area_map(data, area_map)
    
    # Check for errors and try to fix them with fallback logic
    for position, res in result["results"].items():
        if "error" in res and ("đường dẫn không tồn tại" in res["error"] or "Không tìm thấy đơn giá trong node đã chọn" in res["error"]):
            # Try to get price range for partial path
            path = res.get("path", "").split(" > ")
            if len(path) >= 2:  # At least category and material_type
                category = path[0]
                material_type = path[1]
                subtype = path[2] if len(path) > 2 else None
                
                # Try to get price range for the partial path
                price_ranges = get_price_range(category, material_type, subtype)
                if price_ranges["combined_min"] is not None and price_ranges["combined_max"] is not None:
                    # Replace error with price range result
                    # For unit price quotes (area is None), we don't multiply by area
                    if res.get("area") is None:
                        result["results"][position] = {
                            "path": res["path"],
                            "area": None,
                            "budget": res.get("budget"),
                            "type": "range",
                            "material_min": price_ranges["material_min"],
                            "material_max": price_ranges["material_max"],
                            "labor_min": price_ranges["labor_min"],
                            "labor_max": price_ranges["labor_max"],
                            "combined_min": price_ranges["combined_min"],
                            "combined_max": price_ranges["combined_max"]
                        }
                    else:
                        # For area-based quotes, multiply by area
                        parsed_area = parse_area(res.get("area", "10"))
                        if parsed_area is not None:
                            result["results"][position] = {
                                "path": res["path"],
                                "area": res["area"],
                                "budget": res.get("budget"),
                                "type": "range",
                                "material_min": price_ranges["material_min"],
                                "material_max": price_ranges["material_max"],
                                "labor_min": price_ranges["labor_min"],
                                "labor_max": price_ranges["labor_max"],
                                "combined_min": price_ranges["combined_min"],
                                "combined_max": price_ranges["combined_max"],
                                "total_cost_range": f"{price_ranges['combined_min'] * parsed_area:,.0f} - {price_ranges['combined_max'] * parsed_area:,.0f} VND"
                            }
    
    return result

def _format_quote_result(result: dict) -> str:
    """
    Format the quote result as a markdown table based on the quote type.
    """
    # Determine quote type based on whether area is provided and whether it's a detailed quote with budget
    # Only consider area as present if it's not None and not empty
    has_area = any('area' in res and res['area'] for res in result["results"].values() if isinstance(res, dict))
    has_budget = result["summary"].get("total_budget") is not None
    
    if not has_area:
        # Unit price quote (no area provided, only show unit prices and material names)
        output = "# Báo Giá Đơn Vị\n\n"
        output += "| Vị trí | Tên vật liệu | Đơn giá (Vật tư) | Đơn giá (Nhân công) |\n"
        output += "|--------|--------------|------------------|---------------------|\n"
        
        for position, res in result["results"].items():
            if "error" in res:
                output += f"| {position} | - | Lỗi | |\n"
                continue
                
            # Extract material name from path
            path = res.get("path", "").split(" > ")
            material_name = path[-1] if path else "-"
            
            if res["type"] == "specific":
                unit_vt = res["unit_vattu"]
                unit_nc = res["unit_nhancong"]
                
                # Special handling for Sàn gạch with missing labor cost
                if unit_nc is None:
                    output += f"| {position} | {material_name} | {unit_vt:,.0f} VND/m² | Chưa có giá |\n"
                    if res.get("note"):
                        output += f"| | | | *{res['note']}* |\n"
                else:
                    total_unit = unit_vt + unit_nc if unit_nc is not None else unit_vt
                    output += f"| {position} | {material_name} | {unit_vt:,.0f} VND/m² | {unit_nc:,.0f} VND/m² |\n"
            elif res["type"] in ["range", "summary"]:
                # For range/summary, show separate material and labor price ranges
                material_min = res.get("material_min")
                material_max = res.get("material_max")
                labor_min = res.get("labor_min")
                labor_max = res.get("labor_max")
                
                # Format material price range
                if material_min is not None and material_max is not None:
                    if material_min == material_max:
                        material_range = f"{material_min:,.0f} VND"
                    else:
                        material_range = f"{material_min:,.0f} - {material_max:,.0f} VND"
                else:
                    material_range = "N/A"
                
                # Format labor price range
                if labor_min is not None and labor_max is not None:
                    if labor_min == labor_max:
                        labor_range = f"{labor_min:,.0f} VND"
                    else:
                        labor_range = f"{labor_min:,.0f} - {labor_max:,.0f} VND"
                else:
                    labor_range = "Chưa có giá nhân công"
                
                output += f"| {position} | {material_name} | {material_range} | {labor_range} |\n"
        
        return output
    
    elif has_budget:
        # Detailed quote (area and budget provided)
        output = "# Báo Giá Chi Tiết\n\n"
        output += "| Vị trí | Tên vật liệu | Diện tích | Đơn giá (Vật tư) | Đơn giá (Nhân công) | Tổng chi phí |\n"
        output += "|--------|--------------|-----------|------------------|---------------------|--------------|\n"
        
        total_cost = 0
        total_min = 0
        total_max = 0
        
        for position, res in result["results"].items():
            if "error" in res:
                output += f"| {position} | - | Lỗi | | | |\n"
                continue
                
            # Extract material name from path
            path = res.get("path", "").split(" > ")
            material_name = path[-1] if path else "-"
            
            area = res["area"]
            
            if res["type"] == "specific":
                unit_vt = res["unit_vattu"]
                unit_nc = res["unit_nhancong"]
                total = res["total_cost"]
                total_cost += total
                
                # Special handling for Sàn gạch with missing labor cost
                if unit_nc is None:
                    output += f"| {position} | {material_name} | {area} m² | {unit_vt:,.0f} VND/m² | Chưa có giá | {total:,.0f} VND |\n"
                    if res.get("note"):
                        output += f"| | | | | | *{res['note']}* |\n"
                else:
                    output += f"| {position} | {material_name} | {area} m² | {unit_vt:,.0f} VND/m² | {unit_nc:,.0f} VND/m² | {total:,.0f} VND |\n"
            elif res["type"] in ["range", "summary"]:
                # For range/summary, we'll show the range
                range_text = res.get("total_cost_range", "N/A")
                output += f"| {position} | {material_name} | {area} m² | - | - | {range_text} |\n"
                
                # Try to extract min/max for total calculation
                try:
                    range_text_clean = range_text.replace(",", "")
                    if " - " in range_text_clean:
                        min_val, max_val = range_text_clean.split(" - ")
                        total_min += int(min_val.split()[0])
                        total_max += int(max_val.split()[0])
                except:
                    pass
        
        if total_cost > 0:
            output += f"\n**Tổng chi phí: {total_cost:,.0f} VND**\n"
        else:
            output += f"\n**Tổng chi phí ước tính: {total_min:,.0f} - {total_max:,.0f} VND**\n"
        
        if result["summary"].get("total_budget"):
            budget = result["summary"]["total_budget"]
            output += f"**Ngân sách: {budget:,.0f} VND**\n"
            output += f"**Trạng thái: {result['summary'].get('status', 'Không rõ')}**\n"
        
        return output
    
    else:
        # Preliminary quote (area provided but no budget)
        output = "# Báo Giá Sơ Bộ\n\n"
        output += "| Vị trí | Tên vật liệu | Diện tích | Đơn giá (Vật tư) | Đơn giá (Nhân công) | Tổng chi phí |\n"
        output += "|--------|--------------|-----------|------------------|---------------------|--------------|\n"
        
        total_min = 0
        total_max = 0
        
        for position, res in result["results"].items():
            if "error" in res:
                output += f"| {position} | - | Lỗi | | | |\n"
                continue
                
            # Extract material name from path
            path = res.get("path", "").split(" > ")
            material_name = path[-1] if path else "-"
            
            area = res["area"]
            
            if res["type"] == "specific":
                unit_vt = res["unit_vattu"]
                unit_nc = res["unit_nhancong"]
                total = res["total_cost"]
                total_min += total
                total_max += total
                
                # Special handling for Sàn gạch with missing labor cost
                if unit_nc is None:
                    output += f"| {position} | {material_name} | {area} m² | {unit_vt:,.0f} VND/m² | Chưa có giá | {total:,.0f} VND |\n"
                    if res.get("note"):
                        output += f"| | | | | | *{res['note']}* |\n"
                else:
                    output += f"| {position} | {material_name} | {area} m² | {unit_vt:,.0f} VND/m² | {unit_nc:,.0f} VND/m² | {total:,.0f} VND |\n"
            elif res["type"] in ["range", "summary"]:
                # For range/summary, we'll show the range
                range_text = res.get("total_cost_range", "N/A")
                output += f"| {position} | {material_name} | {area} m² | - | - | {range_text} |\n"
                
                # Try to extract min/max for total calculation
                try:
                    range_text_clean = range_text.replace(",", "")
                    if " - " in range_text_clean:
                        min_val, max_val = range_text_clean.split(" - ")
                        total_min += int(min_val.split()[0])
                        total_max += int(max_val.split()[0])
                except:
                    pass
        
        output += f"\n**Tổng chi phí ước tính: {total_min:,.0f} - {total_max:,.0f} VND**\n"
        
        return output

@tool
def propose_options_for_budget(budget: float, room_size: str = None, area: str = None) -> str:
    """
    (Đề xuất theo ngân sách) Đề xuất các phương án vật liệu phù hợp với ngân sách và diện tích.
    Sử dụng khi người dùng cung cấp ngân sách và thông tin diện tích (diện tích cụ thể hoặc kích thước phòng).

    Args:
        budget: Ngân sách (ví dụ: 5000000)
        room_size: Kích thước phòng (ví dụ: "5x10x6" cho dài x rộng x cao)
        area: Diện tích (ví dụ: "20", "5x4") - nếu không có room_size
    """
    print(f"--- INFO: Proposing options for budget {budget}, room_size {room_size}, area {area} ---")
    
    try:
        # Handle area extraction from either room_size or area parameter
        if room_size:
            # Use room_parser to extract per-surface areas
            from .room_parser import create_area_map_from_room_size
            area_map_data = create_area_map_from_room_size(room_size)
            area_map = {"total_budget": budget, "surfaces": area_map_data["surfaces"]}
        elif area:
            # Parse area
            parsed_area = parse_area(area)
            if parsed_area is None:
                return f"Lỗi: Không thể phân tích diện tích '{area}'"
            
            # Create area map with different material categories
            area_map = {
                "total_budget": budget,
                "surfaces": {
                    "Sàn": {
                        "path": ["Sàn"],
                        "area": str(parsed_area)
                    },
                    "Tường": {
                        "path": ["Tường và vách"],
                        "area": str(parsed_area)
                    },
                    "Trần": {
                        "path": ["Trần"],
                        "area": str(parsed_area)
                    }
                }
            }
        else:
            return "Lỗi: Cần cung cấp thông tin diện tích (area) hoặc kích thước phòng (room_size)"
        
        # Use exhaustive search to find best variant for budget
        from .exhaustive_search import find_best_variant_for_budget
        result, status = find_best_variant_for_budget(DATABASE, area_map, budget)
        
        if result is None:
            return f"Lỗi: {status}"
        
        # Format result
        formatted_result = _format_quote_result(result)
        
        return formatted_result
    except Exception as e:
        error_msg = f"Lỗi khi thực thi công cụ 'propose_options_for_budget': {str(e)}"
        print(error_msg)
        return error_msg

# --- Unified Tools List ---

TOOLS = {
    "get_internal_price": get_internal_price_new,
    "get_market_price": get_market_price_new,
    "get_saved_quotes": get_saved_quotes_new,
    "save_quote_to_file": save_quote_to_file_new,
    "search_materials": search_materials_new,
    "get_categories": get_categories_new,
    "get_material_types": get_material_types_new,
    "get_material_subtypes": get_material_subtypes_new,
    "generate_quote_from_image": generate_quote_from_image,
    "propose_options_for_budget": propose_options_for_budget,
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
