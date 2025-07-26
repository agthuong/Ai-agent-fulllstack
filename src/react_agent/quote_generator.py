"""
Các hàm tạo báo giá dựa trên các hạng mục vật liệu
"""
import json
import os
import logging
from datetime import datetime
import re
from typing import Optional, List, Dict, Any, Tuple
import itertools

# Thiết lập logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Constants ---
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data_new')
VIETNAMESE_MATERIAL_MAP = {
    "gỗ": "wood", "sơn": "paint", "đá": "stone", "giấy dán tường": "wallpaper"
}

# --- Parsing Utilities ---

def parse_area(area_str: Optional[str]) -> float:
    """
    Parses an area string with various formats and units, returning the area in square meters (m²).
    Handles formats like: "30m2", "50 mét vuông", "12m²". This version is corrected
    to not mistakenly concatenate numbers from the unit.
    """
    if not area_str: 
        return 0.0
    
    normalized_str = str(area_str).lower()
    normalized_str = normalized_str.replace("mét vuông", "m2").replace("vuông", "m2")
    
    # This regex finds the first group of digits, ignoring later ones (like the '2' in 'm2').
    numbers = re.findall(r'(\d+\.?\d*)', normalized_str)
    
    if not numbers:
        return 0.0
    
    try:
        # Take the first number found.
        value = float(numbers[0])
        
        if "cm2" in normalized_str or "cm" in normalized_str:
            return value / 10000
        
        return value
    except (ValueError, IndexError):
        return 0.0

def parse_budget(budget_str: Optional[str]) -> float:
    if not budget_str: return 0.0
    budget_str = str(budget_str).lower()
    multipliers = {
        'k': 1_000, 'nghìn': 1_000, 'ngàn': 1_000,
        'tr': 1_000_000, 'triệu': 1_000_000,
        'tỷ': 1_000_000_000, 'tỉ': 1_000_000_000, 'ty': 1_000_000_000
    }
    value = float(re.findall(r'(\d+\.?\d*)', budget_str)[0])
    for key, mul in multipliers.items():
        if key in budget_str:
            return value * mul
    return value

# --- Data Loading ---

def _load_material_data(material_type: str) -> Optional[Dict]:
    filename_en = VIETNAMESE_MATERIAL_MAP.get(material_type.lower())
    if not filename_en: return None
    file_path = os.path.join(DATA_DIR, f"{filename_en}.json")
    if not os.path.exists(file_path): return None
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _get_all_variants(material_type: str, specific_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Loads all variants for a material, optionally filtered by a specific type."""
    data = _load_material_data(material_type)
    if not data: return []
    
    variants = []
    target_data = data.get(specific_type, data) if specific_type else data

    for parent_type, type_data in ([(specific_type, target_data)] if specific_type else target_data.items()):
        if not isinstance(type_data, dict): continue
        for variant_name, price_str in type_data.items():
            try:
                price_val = float(re.match(r'[\d,.]+', price_str.replace(',', '')).group(0))
                variants.append({
                    "material_type": material_type,
                    "parent_type": parent_type,
                    "variant": variant_name,
                    "price": price_val
                })
            except (ValueError, AttributeError):
                continue
    return variants

# --- Quote Generation Logic ---

def generate_preliminary_quote(components: List[Dict[str, Any]]) -> str:
    """
    Tạo báo giá sơ bộ chi tiết cho từng hạng mục vật liệu, bao gồm cả vị trí.
    Hàm này không nhóm các vật liệu giống nhau lại.
    """
    if not components:
        return "Không có hạng mục nào để báo giá."

    table_rows = []
    
    for item in components:
        material_type = item.get("material_type", "N/A")
        specific_type = item.get("type")
        position = item.get("position", "N/A")
        
        price_range_str = "Không có dữ liệu" # Default
        data = _load_material_data(material_type)

        if data:
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
                        price_range_str = f"{min_price:,.0f} - {max_price:,.0f} VND/m²"
                else:
                    price_range_str = "Chưa có giá chi tiết"
            
            except Exception as e:
                logger.error(f"Lỗi khi xử lý giá cho '{material_type}': {e}")
                price_range_str = "Lỗi xử lý dữ liệu"

        table_rows.append(
            f"| {material_type.title()} | {specific_type or 'Tất cả'} | {position.title()} | {price_range_str} |"
        )

    header = "| Vật liệu | Loại | Vị trí | Đơn giá (Ước tính) |\n|---|---|---|---|"
    body = "\n".join(table_rows)
    
    return f"# Báo Giá Sơ Bộ\n\n{header}\n{body}\n\n*Ghi chú: Đây là báo giá sơ bộ, vui lòng cung cấp diện tích để có báo giá chi tiết.*"

def generate_area_quote(components: List[Dict[str, Any]]) -> str:
    """
    Tạo báo giá dựa trên danh sách các hạng mục và diện tích của từng hạng mục
    
    Args:
        components: Danh sách các hạng mục vật liệu, mỗi hạng mục có thể có diện tích riêng và vị trí
            [{"material_type": "gỗ", "type": "óc chó", "area": "20m2", "position": "sàn"}, 
             {"material_type": "đá", "type": "marble", "area": "15m2", "position": "tường phía đối diện"}]
            
    Returns:
        str: Báo giá theo diện tích đã định dạng
    """
    import os
    import json
    import logging
    import re
    
    if not components:
        return "Không có hạng mục nào để báo giá."
    
    # Map loại vật liệu tiếng Việt sang tên file tiếng Anh
    material_map = {
        'sơn': 'paint',
        'gỗ': 'wood',
        'đá': 'stone',
        'giấy dán tường': 'wallpaper',
        'gạch': 'tile'
    }
    
    # Đường dẫn tới thư mục dữ liệu
    data_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data_new')
    
    results = []
    total_min_cost = 0
    total_max_cost = 0
    
    # Xử lý từng hạng mục
    for component in components:
        material_type = component.get("material_type")
        if not material_type:
            logging.warning(f"Missing material_type in component: {component}")
            continue
            
        specific_type = component.get("type")
        area_str = component.get("area")
        position = component.get("position", "không xác định")
        
        if not area_str:
            logging.info(f"No area specified for {material_type}, skipping cost calculation")
            results.append({
                "material": material_type,
                "type": specific_type,
                "position": position,
                "area": None,
                "price_range": "Cần diện tích để tính chi phí",
                "estimated_cost": None
            })
            continue
            
        # Parse diện tích
        try:
            area_value = parse_area(area_str)
        except ValueError:
            logging.warning(f"Could not parse area from '{area_str}' for {material_type}")
            results.append({
                "material": material_type,
                "type": specific_type,
                "position": position,
                "area": area_str,
                "price_range": "Không thể xác định diện tích",
                "estimated_cost": None
            })
            continue
            
        # Tìm file dữ liệu giá
        material_key = material_type.lower()
        if material_key not in material_map:
            logging.warning(f"Unsupported material type: {material_type}")
            results.append({
                "material": material_type,
                "type": specific_type,
                "position": position,
                "area": area_str,
                "price_range": "Không hỗ trợ loại vật liệu này",
                "estimated_cost": None
            })
            continue
            
        file_path = os.path.join(data_dir, f"{material_map[material_key]}.json")
        if not os.path.exists(file_path):
            logging.warning(f"Material data file not found: {file_path}")
            results.append({
                "material": material_type,
                "type": specific_type,
                "position": position,
                "area": area_str,
                "price_range": "Không tìm thấy dữ liệu giá",
                "estimated_cost": None
            })
            continue
            
        try:
            # Đọc dữ liệu giá
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Lọc theo loại cụ thể hoặc lấy tất cả
            price_data = {}
            if specific_type and specific_type.lower() != "null" and specific_type in data:
                price_data = {specific_type: data[specific_type]}
            else:
                price_data = data
                
            # Trích xuất giá cho loại vật liệu
            if not price_data:
                logging.warning(f"No price data found for {material_type}/{specific_type}")
                results.append({
                    "material": material_type,
                    "type": specific_type,
                    "position": position,
                    "area": area_str,
                    "price_range": "Không tìm thấy dữ liệu giá",
                    "estimated_cost": None
                })
                continue
                
            # Tính toán min/max/avg price
            all_prices = []
            for type_name, type_data in price_data.items():
                for variant, price_str in type_data.items():
                    # Parse giá từ chuỗi, giữ lại phần số và dấu phẩy
                    price_match = re.search(r'([\d,\.]+)', price_str)
                    if price_match:
                        numeric_str = price_match.group(1)
                        # Chuyển đổi string thành số float (loại bỏ dấu phẩy hàng nghìn)
                        price_val = float(numeric_str.replace(',', ''))
                        all_prices.append((type_name, variant, price_val, price_str))
            
            if not all_prices:
                logging.warning(f"Could not parse any prices for {material_type}/{specific_type}")
                results.append({
                    "material": material_type,
                    "type": specific_type,
                    "position": position,
                    "area": area_str,
                    "price_range": "Lỗi định dạng giá",
                    "estimated_cost": None
                })
                continue
                
            # Tính giá min, max và trung bình
            min_price = min(all_prices, key=lambda x: x[2])
            max_price = max(all_prices, key=lambda x: x[2])
            avg_price = sum(p[2] for p in all_prices) / len(all_prices)
            
            # Tính chi phí dựa trên diện tích
            min_cost = min_price[2] * area_value
            max_cost = max_price[2] * area_value
            avg_cost = avg_price * area_value
            
            # Thêm vào kết quả
            price_range_str = f"{min_price[3]} - {max_price[3]}"
            cost_range_str = f"{min_cost:,.0f} - {max_cost:,.0f} VND"
            
            results.append({
                "material": material_type,
                "type": specific_type if specific_type and specific_type.lower() != "null" else "Tất cả các loại",
                "position": position,
                "area": area_str,
                "area_value": area_value,
                "price_range": price_range_str,
                "min_price": min_price[2],
                "max_price": max_price[2],
                "min_price_display": min_price[3],
                "max_price_display": max_price[3],
                "avg_price": avg_price,
                "min_cost": min_cost,
                "max_cost": max_cost,
                "avg_cost": avg_cost,
                "cost_range": cost_range_str
            })
            
            # Cộng vào tổng chi phí (dùng giá trung bình)
            total_min_cost += min_cost
            total_max_cost += max_cost
            
        except Exception as e:
            logging.error(f"Error processing {material_type}/{specific_type}: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            
            results.append({
                "material": material_type,
                "type": specific_type,
                "position": position,
                "area": area_str,
                "price_range": f"Lỗi xử lý: {str(e)}",
                "estimated_cost": None
            })
    
    # Tạo báo cáo
    report = []
    report.append("# Báo Giá Chi Tiết Theo Diện Tích")
    report.append("")
    
    # Nhóm kết quả theo vị trí
    position_groups = {}
    for item in results:
        position = item["position"]
        if position not in position_groups:
            position_groups[position] = []
        position_groups[position].append(item)
    
    # Bảng tổng quan
    report.append("| Vật liệu | Loại | Vị trí | Diện tích | Đơn giá | Chi phí ước tính |")
    report.append("|----------|------|--------|-----------|---------|------------------|")
    
    for item in results:
        material = item["material"]
        type_str = item["type"] or "N/A"
        position = item["position"] or "N/A"
        area = item["area"] or "N/A"
        price_range = item["price_range"]
        
        # Xử lý trường hợp không tính được chi phí
        if "cost_range" in item:
            cost = item["cost_range"]
        else:
            cost = "Không xác định"
            
        report.append(f"| {material} | {type_str} | {position} | {area} | {price_range} | {cost} |")
    
    # Tổng chi phí theo vị trí
    if len(position_groups) > 1:
        report.append("")
        report.append("## Chi Phí Theo Vị Trí")
        for position, items in position_groups.items():
            # Note: The per-position cost is still based on average for simplicity.
            # A min-max range per position could also be implemented if needed.
            position_total = sum(item.get("avg_cost", 0) for item in items if "avg_cost" in item)
            if position_total > 0:
                report.append(f"- **{position}**: {position_total:,.0f} VND")
    
    # Tổng chi phí
    report.append("")
    report.append(f"## Tổng Chi Phí Ước Tính: {total_min_cost:,.0f} - {total_max_cost:,.0f} VND")
    report.append("")
    report.append("*Ghi chú: Chi phí được tính dựa trên khoảng giá thấp nhất và cao nhất của các loại vật liệu.*")
    report.append("*Báo giá chỉ tính chi phí vật liệu, chưa bao gồm nhân công và các chi phí phát sinh khác.*")
    
    return "\n".join(report)

def generate_budget_quote(material_type: str, budget: float, area: float, specific_type: Optional[str] = None) -> str:
    """
    Finds the best single material variant that fits a budget for a given area.
    """
    print(f"--- Generating budget quote for '{material_type}' (Type: {specific_type}) with Budget: {budget:,.0f} and Area: {area}m² ---")
    if area <= 0:
        return "Lỗi: Diện tích phải là một số dương để tính báo giá theo ngân sách."

    budget_per_sqm = budget / area
    all_variants = _get_all_variants(material_type, specific_type)

    if not all_variants:
        return f"Không tìm thấy thông tin giá chi tiết cho vật liệu '{material_type}' (Loại: {specific_type or 'Tất cả'})."

    # Filter for options within budget
    valid_options = [v for v in all_variants if v["price"] <= budget_per_sqm]

    if not valid_options:
        min_price_variant = min(all_variants, key=lambda x: x['price'])
        return (f"Rất tiếc, không có lựa chọn nào cho '{material_type}' phù hợp với ngân sách của bạn.\n"
                f"- Ngân sách mỗi m²: {budget_per_sqm:,.0f} VND\n"
                f"- Lựa chọn rẻ nhất '{min_price_variant['variant']}' có giá: {min_price_variant['price']:,.0f} VND/m².")

    # Find the best option (most expensive within budget)
    best_option = max(valid_options, key=lambda x: x["price"])
    total_cost = best_option["price"] * area

    response = (
        f"Với ngân sách {budget:,.0f} VND cho {area} m², đề xuất tốt nhất cho bạn là:\n\n"
        f"| Hạng mục | Loại chi tiết | Đơn giá | Tổng chi phí |\n"
        f"|---|---|---|---|\n"
        f"| {material_type.title()} | **{best_option['parent_type']} - {best_option['variant']}** | {best_option['price']:,.0f} VND/m² | {total_cost:,.0f} VND |"
    )
    return response 

def _get_all_variants_for_component(component: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Helper to get all possible variants for a single component, including price and area."""
    material_type = component.get("material_type")
    specific_type = component.get("type")
    area = parse_area(component.get("area", "0"))

    if area <= 0:
        return []

    data = _load_material_data(material_type)
    if not data:
        return []

    variants = []
    # If a specific type is given, only look within that type. Otherwise, look through all types.
    target_data = {}
    if specific_type:
        # Case-insensitive lookup for the specific type
        for key, value in data.items():
            if key.lower() == specific_type.lower():
                target_data[key] = value
                break
    else:
        target_data = data

    for parent_type, type_data in target_data.items():
        if not isinstance(type_data, dict):
            continue
        for variant_name, price_str in type_data.items():
            try:
                price_match = re.search(r'([\d,.]+)', str(price_str).replace(',', ''))
                if price_match:
                    price_val = float(price_match.group(1))
                    variants.append({
                        "position": component.get("position", "N/A"),
                        "material_type": material_type,
                        "parent_type": parent_type,
                        "variant": variant_name,
                        "price": price_val,
                        "area": area
                    })
            except (ValueError, AttributeError):
                continue
    return variants

def calculate_optimal_combinations(components: List[Dict[str, Any]], total_budget: float) -> str:
    """
    Finds the top 2 optimal combinations of materials for multiple components that fit within a total budget.
    This function performs a combinatorial search to find the best overall solutions.
    """
    logger.info(f"Starting optimal combination search for {len(components)} components with budget {total_budget:,.0f} VND.")

    # 1. Get all possible material choices for each component.
    variants_per_component = [_get_all_variants_for_component(c) for c in components]

    # Check if any component has no variants, which makes a solution impossible.
    if not all(variants_per_component):
        empty_components = [c.get('position', 'Unknown') for c, v in zip(components, variants_per_component) if not v]
        logger.warning(f"No variants found for components: {empty_components}. Cannot find a combination.")
        return f"Lỗi: Không tìm thấy bất kỳ lựa chọn vật liệu nào cho các hạng mục: {', '.join(empty_components)}. Không thể tạo tổ hợp báo giá."

    # 2. Generate all possible combinations (Cartesian product).
    # This can be memory-intensive. For a real-world app, consider sampling or optimization heuristics.
    logger.info("Generating all possible combinations...")
    all_combinations = itertools.product(*variants_per_component)

    # 3. Calculate the total cost for each combination and filter those within budget.
    valid_combinations = []
    cheapest_combination = None
    min_cost_so_far = float('inf')

    for i, combo in enumerate(all_combinations):
        total_cost = sum(variant['price'] * variant['area'] for variant in combo)
        
        # Track the cheapest combination overall, regardless of budget
        if total_cost < min_cost_so_far:
            min_cost_so_far = total_cost
            cheapest_combination = {'combo': combo, 'total_cost': total_cost}
            
        if total_cost <= total_budget:
            valid_combinations.append({'combo': combo, 'total_cost': total_cost})
        if (i + 1) % 10000 == 0:
            logger.info(f"Processed {i+1} combinations...")
    
    logger.info(f"Found {len(valid_combinations)} valid combinations within budget. Cheapest possible option costs {min_cost_so_far:,.0f} VND.")

    if not valid_combinations:
        if cheapest_combination:
            response_parts = [
                f"Rất tiếc, không có phương án nào phù hợp với ngân sách {total_budget:,.0f} VND.",
                f"Dưới đây là **phương án có chi phí thấp nhất** mà chúng tôi tìm được (vượt ngân sách của bạn):\n",
                f"## Phương án Rẻ nhất (Tổng chi phí: {cheapest_combination['total_cost']:,.0f} VND)\n"
            ]
            table_header = "| Vị trí | Vật liệu | Loại chi tiết | Đơn giá (VND/m²) | Chi phí (VND) |"
            table_separator = "|---|---|---|---|---|"
            table_rows = [table_header, table_separator]
            
            for variant_details in cheapest_combination['combo']:
                item_cost = variant_details['price'] * variant_details['area']
                row = (f"| {variant_details['position'].title()} "
                       f"| {variant_details['material_type'].title()} "
                       f"| {variant_details['parent_type']} - {variant_details['variant']} "
                       f"| {variant_details['price']:,.0f} "
                       f"| {item_cost:,.0f} |")
                table_rows.append(row)
            
            response_parts.append("\n".join(table_rows))
            response_parts.append("\n*Gợi ý: Bạn có thể cân nhắc tăng ngân sách hoặc thay đổi yêu cầu vật liệu để có nhiều lựa chọn hơn.*")
            return "\n".join(response_parts)
        else:
            return (f"Rất tiếc, không tìm thấy tổ hợp vật liệu nào. "
                    "Vui lòng kiểm tra lại yêu cầu vật liệu.")

    # 4. Sort the valid combinations by total cost in descending order to find the ones closest to the budget.
    valid_combinations.sort(key=lambda x: x['total_cost'], reverse=True)

    # 5. Get the top 2 options.
    top_options = valid_combinations[:2]

    # 6. Format the final response string.
    response_parts = [f"# Đề xuất các phương án tối ưu cho ngân sách {total_budget:,.0f} VND\n"]

    for i, option in enumerate(top_options):
        response_parts.append(f"## Phương án {i+1} (Tổng chi phí: {option['total_cost']:,.0f} VND)\n")
        table_header = "| Vị trí | Vật liệu | Loại chi tiết | Diện tích (m²) | Đơn giá (VND/m²) | Chi phí (VND) |"
        table_separator = "|---|---|---|---|---|---|"
        table_rows = [table_header, table_separator]
        
        for variant_details in option['combo']:
            item_cost = variant_details['price'] * variant_details['area']
            row = (f"| {variant_details['position'].title()} "
                   f"| {variant_details['material_type'].title()} "
                   f"| {variant_details['parent_type']} - {variant_details['variant']} "
                   f"| {variant_details['area']:.2f} "
                   f"| {variant_details['price']:,.0f} "
                   f"| {item_cost:,.0f} |")
            table_rows.append(row)
        
        response_parts.append("\n".join(table_rows))
        response_parts.append("\n")

    return "\n".join(response_parts) 