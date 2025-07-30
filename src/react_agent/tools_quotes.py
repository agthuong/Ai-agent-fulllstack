import json
import re

# === PARSE AREA ===
def parse_area(area_input):
    try:
        if isinstance(area_input, (int, float)):
            return float(area_input)
        if isinstance(area_input, str):
            area_input = area_input.lower().replace("m²", "").replace("m2", "").replace("m", "").strip()
            numbers = re.findall(r"[\d\.]+", area_input)

            if 'x' in area_input:
                if len(numbers) != 2:
                    return None  # for situations like "5x" or "x2"
                return float(numbers[0]) * float(numbers[1])
            elif len(numbers) == 1:
                return float(numbers[0])
    except:
        pass
    return None

# === FIND PRICE RANGE WITH VẬT TƯ + NHÂN CÔNG ===
def find_price_range(node):
    vt_prices = []
    nc_prices = []

    def collect_prices(subnode):
        if isinstance(subnode, dict):
            if "Vật tư" in subnode:
                vt = subnode["Vật tư"]
                nc = subnode.get("Nhân công", 0)
                vt_prices.append(vt)
                nc_prices.append(nc)
            else:
                for v in subnode.values():
                    collect_prices(v)
        elif isinstance(subnode, list):
            for item in subnode:
                collect_prices(item)

    collect_prices(node)

    if vt_prices and nc_prices:
        return (
            (min(vt_prices), max(vt_prices)),
            (min(nc_prices), max(nc_prices))
        )
    return (None, None), (None, None)

# === WALK JSON PATH ===
def resolve_path(data, path):
    """
    Walk a JSON path and return the node if found.
    Supports flexible path matching by searching within the database structure.
    """
    # First try the exact path
    node = data
    for key in path:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            node = None
            break
    
    if node is not None:
        return node
    
    # If exact path doesn't work, search for the best match
    # We'll do a recursive search through the database structure
    def search_node(current_node, remaining_path):
        if not remaining_path:
            # If we've consumed all path elements, check if this node has pricing info
            if isinstance(current_node, dict) and "Vật tư" in current_node:
                return current_node
            return None
        
        current_key = remaining_path[0]
        rest_path = remaining_path[1:]
        
        if isinstance(current_node, dict):
            # Try exact match first
            if current_key in current_node:
                result = search_node(current_node[current_key], rest_path)
                if result is not None:
                    return result
            
            # If exact match fails, try fuzzy matching
            # Look for nodes that contain the current key as a substring
            for key, value in current_node.items():
                if isinstance(value, dict):
                    # Check if the key matches or contains the target
                    if current_key.lower() in key.lower() or key.lower() in current_key.lower():
                        result = search_node(value, rest_path)
                        if result is not None:
                            return result
                    
                    # If that fails, recursively search deeper
                    result = search_node(value, remaining_path)
                    if result is not None:
                        return result
        
        return None
    
    # Start the search from the root
    return search_node(data, path)

# === CALCULATE FOR ONE SURFACE ===
def calculate_cost(data, path, area, budget=None, cost_type="all"):
    # Handle unit price quotes (when area is None)
    if area is None:
        node = resolve_path(data, path)
        if node is None:
            return {
                "error": "Invalid path: đường dẫn không tồn tại",
                "path": " > ".join(path),
                "area": area,
                "budget": budget
            }

        result = {
            "path": " > ".join(path),
            "area": area,
            "budget": budget
        }

        if isinstance(node, dict) and "Vật tư" in node:
            vt = node["Vật tư"]
            nc = node.get("Nhân công")
            
            # Special handling for "Sàn gạch" - if labor cost is missing, only show material cost
            if len(path) >= 2 and path[0] == "Sàn" and path[1] == "Sàn gạch" and "Nhân công" not in node:
                result.update({
                    "type": "specific",
                    "unit_vattu": vt,
                    "unit_nhancong": None,
                    "note": "Chưa có giá nhân công cho loại vật liệu này"
                })
            else:
                if cost_type == "vat_tu":
                    nc = 0 if nc is not None else None
                elif cost_type == "nhan_cong":
                    vt = 0 if vt is not None else None
                result.update({
                    "type": "specific",
                    "unit_vattu": vt,
                    "unit_nhancong": nc
                })
        else:
            result["error"] = "Không tìm thấy đơn giá trong node đã chọn"
        
        return result
    
    # Handle regular quotes (when area is provided)
    parsed_area = parse_area(area)
    if parsed_area is None:
        return {
            "error": "Invalid area input: sai định dạng diện tích",
            "path": " > ".join(path),
            "area": area,
            "budget": budget
        }

    node = resolve_path(data, path)
    if node is None:
        return {
            "error": "Invalid path: đường dẫn không tồn tại",
            "path": " > ".join(path),
            "area": parsed_area,
            "budget": budget
        }

    result = {
        "path": " > ".join(path),
        "area": parsed_area,
        "budget": budget
    }

    if isinstance(node, dict) and "Vật tư" in node:
        vt = node["Vật tư"]
        nc = node.get("Nhân công", 0)
        
        # Special handling for "Sàn gạch" - if labor cost is missing, only show material cost
        if len(path) >= 2 and path[0] == "Sàn" and path[1] == "Sàn gạch" and "Nhân công" not in node:
            total = vt * parsed_area
            result.update({
                "type": "specific",
                "unit_vattu": vt,
                "unit_nhancong": None,
                "total_vattu": vt * parsed_area,
                "total_nhancong": None,
                "total_cost": total,
                "note": "Chưa có giá nhân công cho loại vật liệu này"
            })
        else:
            if cost_type == "vat_tu":
                nc = 0
            elif cost_type == "nhan_cong":
                vt = 0
            total = (vt + nc) * parsed_area
            result.update({
                "type": "specific",
                "unit_vattu": vt,
                "unit_nhancong": nc,
                "total_vattu": vt * parsed_area,
                "total_nhancong": nc * parsed_area,
                "total_cost": total
            })
    elif len(path) == 0:
        result["type"] = "summary"
        (vt_min, vt_max), (nc_min, nc_max) = find_price_range(node)
        if vt_min is not None:
            if cost_type == "vat_tu":
                min_total = vt_min
                max_total = vt_max
            elif cost_type == "nhan_cong":
                min_total = nc_min
                max_total = nc_max
            else:
                min_total = vt_min + nc_min
                max_total = vt_max + nc_max
            result.update({
                "unit_price_range": f"{min_total:,} - {max_total:,} VND",
                "total_cost_range": f"{min_total * parsed_area:,} - {max_total * parsed_area:,} VND"
            })
    else:
        (vt_min, vt_max), (nc_min, nc_max) = find_price_range(node)
        if vt_min is not None:
            if cost_type == "vat_tu":
                min_total = vt_min
                max_total = vt_max
            elif cost_type == "nhan_cong":
                min_total = nc_min
                max_total = nc_max
            else:
                min_total = vt_min + nc_min
                max_total = vt_max + nc_max
            result.update({
                "type": "range",
                "unit_price_range": f"{min_total:,} - {max_total:,} VND",
                "total_cost_range": f"{min_total * parsed_area:,} - {max_total * parsed_area:,} VND"
            })
            if budget is not None:
                max_allowable = budget / parsed_area
                if max_total < max_allowable:
                    result["note"] = "Tất cả tùy chọn trong phạm vi ngân sách."
                elif min_total > max_allowable:
                    result["note"] = "Không có tùy chọn nào trong phạm vi ngân sách."
                else:
                    result["note"] = "Một số tùy chọn phù hợp trong phạm vi ngân sách."
        else:
            result["error"] = "Không tìm thấy đơn giá trong node đã chọn"

    return result

# === CALCULATE ALL SURFACES (cho phép cost_type riêng từng surface) ===
def calculate_from_area_map(data, area_map, default_cost_type="all"):
    surfaces = area_map.get("surfaces", {})
    total_budget = area_map.get("total_budget", None)
    results = {}
    total_min = 0
    total_max = 0

    for position, surface in surfaces.items():
        path = surface.get("path")
        area = surface.get("area")
        budget = surface.get("budget", None)
        cost_type = surface.get("cost_type", default_cost_type)
        result = calculate_cost(data, path, area, budget, cost_type=cost_type)
        result["position"] = position
        results[position] = result

        if "error" in result:
            continue
        if result.get("type") == "specific":
            # For unit price quotes, total_cost might not be present
            if "total_cost" in result:
                total_min += result["total_cost"]
                total_max += result["total_cost"]
        elif result.get("type") in ["range", "summary"]:
            try:
                # Extract numeric values from range text like "1,100,000.0 - 257,500,000.0 VND"
                range_text = result.get("total_cost_range", "0 - 0")
                range_parts = range_text.split(" - ")
                if len(range_parts) == 2:
                    # Extract min value (before " - ")
                    min_text = range_parts[0].replace(",", "")
                    # Extract max value (after " - " but before " VND")
                    max_text = range_parts[1].split(" ")[0].replace(",", "")
                    
                    # Convert to float first, then to int
                    total_min += int(float(min_text))
                    total_max += int(float(max_text))
            except Exception as e:
                # Log error for debugging but don't crash
                print(f"Warning: Could not parse range text '{range_text}': {e}")
                pass

    group_summary = {
        "total_budget": total_budget,
        "total_cost_min": total_min,
        "total_cost_max": total_max
    }

    if total_budget is not None:
        if total_max <= total_budget:
            group_summary["status"] = "Tổng chi phí NẰM TRONG ngân sách."
        elif total_min > total_budget:
            group_summary["status"] = "Tổng chi phí VƯỢT ngân sách."
        else:
            group_summary["status"] = "Có khả năng nằm trong ngân sách, một vài vật liệu vượt ngân sách."

    return {"results": results, "summary": group_summary}

# === DISPLAY ===
def print_area_map_result(result):
    print("\nBẢNG BÁO GIÁ DBPLUS")
    for position, res in result["results"].items():
        print(f"\n--- 🔹 {position} ---")
        if "error" in res:
            print(f"Lỗi: {res['error']}")
            continue
        print(f"Vị trí: {position}")
        print(f"Diện tích: {res['area']} m²")
        print(f"Đường dẫn: {res['path']}")
        if res.get("budget"):
            print(f"Ngân sách riêng: {res['budget']:,} VND")
        if res["type"] == "specific":
            print(f"Vật tư: {res['unit_vattu']:,} VND/m²")
            print(f"Nhân công: {res['unit_nhancong']:,} VND/m²")
            print(f"Tổng vật tư: {res['total_vattu']:,} VND")
            print(f"Tổng nhân công: {res['total_nhancong']:,} VND")
            print(f"Tổng chi phí: {res['total_cost']:,} VND")
        elif res["type"] in ["range", "summary"]:
            print(f"Khoảng đơn giá: {res['unit_price_range']}")
            print(f"Khoảng tổng chi phí: {res['total_cost_range']}")
            if "note" in res:
                print(f"Ghi chú: {res['note']}")

    summary = result["summary"]
    print("\nTỔNG KẾT CHI PHÍ:")
    print(f"Tổng dự kiến: {summary['total_cost_min']:,} - {summary['total_cost_max']:,} VND")
    if summary.get("total_budget") is not None:
        print(f"Ngân sách tổng: {summary['total_budget']:,} VND")
        print(f"Trạng thái ngân sách: {summary.get('status', 'Không rõ')}")

    print("\n📤 JSON FORMAT:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
# === MAIN ===
if __name__ == "__main__":
    with open("DatabaseNoiThat.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    area_map = {
        "total_budget": 160000000,
        "surfaces": {
            "Floor": {
                "path": ["Sàn", "Sàn gỗ", "Gỗ công nghiệp"],
                "area": "4x5"
                # cost_type không khai báo -> mặc định là "all"
            },
            "Wall2": {
                "path": ["Tường và vách"],
                "area": "6x2",
                "budget": 6000000,
                "cost_type": "vat_tu"  # Chỉ tính vật tư
            },
            "Wall3": {
                "path": ["Sơn", "Sơn nước", "Bã bột Việt Mỹ, 1 lớp sơn lót"],
                "area": "5x2.5"
                # cost_type mặc định
            },
            "Whole Project": {
                "path": [],
                "area": "100",
                "cost_type": "nhan_cong"  # Chỉ tính nhân công
            }
        }
    }

    print("\n============================ [TEST 1] ============================\n")
    result = calculate_from_area_map(data, area_map)  # Không cần cost_type nữa
    print_area_map_result(result)

    area_map2 = {
        "total_budget": 160000000,
        "surfaces": {
            "Floor": {
                "path": ["Sàn", "Sàn gạch", "Gạch cao cấp"],
                "area": "4x5"
            },
            "Wall2": {
                "path": ["Sàn", "Sàn đá", "Đá nung kết"],
                "area": "6x2",
                "budget": 6000000,
                "cost_type": "vat_tu"
            },
            "Wall3": {
                "path": ["Tường và vách", "Vách thạch cao khung xương 75/76"],
                "area": "5x2.5"
            },
            "Whole Project": {
                "path": ["Tường và vách", "Vách kính cường lực", "Kính cường lực trong", "Malay trong 10 bo cong"],
                "area": "100",
                "cost_type": "nhan_cong"
            },
            "Kitchen": {
                "path": ["Trần", "Trần thạch cao", "Khung xương M29", "tấm thạch cao 9mm"],
                "area": "3x4",
                "budget": 8000000
            },
            "Bathroom": {
                "path": ["Trần"],
                "area": "2x3",
                "budget": 3000000,
                "cost_type": "vat_tu"
            },
            "Living Room": {
                "path": ["Cầu thang", "Ốp gỗ cầu thang", "Sàn gỗ Đỏ/Teak dày 20mm"],
                "area": "5x6",
                "budget": 7000000
            },
            "Bedroom": {
                "path": ["Sơn", "Sơn nước sơn lại trên nền đã có"],
                "area": "4x5",
                "budget": 6000000
            },
            "Dining Room": {
                "path": ["ko có"],
                "area": "4x4",
                "budget": 5000000
            },
            "Garage": {
                "path": ["Garage"],
                "area": "4x5",
                "budget": 6000000,
                "cost_type": "nhan_cong"
            }
        }
    }

    print("\n============================ [TEST 2] ============================\n")
    result2 = calculate_from_area_map(data, area_map2)
    print_area_map_result(result2)
