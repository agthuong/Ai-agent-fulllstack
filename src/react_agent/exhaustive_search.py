"""Exhaustive search utilities for budget-based material selection."""

from typing import Dict, List, Tuple, Any


def get_all_variant_paths(data: Dict, current_path: List[str] = None) -> List[List[str]]:
    """
    Get all paths to variant nodes in the database.
    A variant node is one that contains 'Vật tư' price.
    
    Args:
        data: Database dictionary
        current_path: Current path being traversed
    
    Returns:
        List of paths to variant nodes
    """
    if current_path is None:
        current_path = []
    
    paths = []
    
    # If this is a variant node (has 'Vật tư' price)
    if isinstance(data, dict) and 'Vật tư' in data:
        paths.append(current_path)
    
    # Recursively traverse children
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                paths.extend(get_all_variant_paths(value, current_path + [key]))
    
    return paths


def get_variant_info(data: Dict, path: List[str]) -> Dict:
    """
    Get variant information (Vật tư, Nhân công prices) from a path.
    
    Args:
        data: Database dictionary
        path: Path to variant node
    
    Returns:
        Dictionary with variant info or None if not found
    """
    node = data
    for part in path:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    
    if isinstance(node, dict) and 'Vật tư' in node:
        return {
            'path': path,
            'unit_vattu': node['Vật tư'],
            'unit_nhancong': node.get('Nhân công', 0)
        }
    
    return None


def calculate_total_cost_for_variant(
    data: Dict, 
    area_map: Dict, 
    variant_path: List[str]
) -> Tuple[float, Dict]:
    """
    Calculate total cost for all surfaces using the same variant.
    
    Args:
        data: Database dictionary
        area_map: Area map with surface areas
        variant_path: Path to variant to use for all surfaces
    
    Returns:
        Tuple of (total_cost, surface_details)
    """
    total_cost = 0
    surface_details = {}
    
    # Get variant info
    variant_info = get_variant_info(data, variant_path)
    if not variant_info:
        return float('inf'), {}
    
    unit_vt = variant_info['unit_vattu']
    unit_nc = variant_info['unit_nhancong']
    
    # Calculate cost for each surface
    for position, surface in area_map.get('surfaces', {}).items():
        area = float(surface.get('area', 0))
        surface_cost = (unit_vt + unit_nc) * area
        total_cost += surface_cost
        
        surface_details[position] = {
            'path': ' > '.join(variant_path),
            'area': area,
            'unit_vattu': unit_vt,
            'unit_nhancong': unit_nc,
            'total_cost': surface_cost,
            'type': 'specific'
        }
    
    return total_cost, surface_details


def find_best_variant_for_budget(
    data: Dict, 
    area_map: Dict, 
    budget: float
) -> Tuple[Dict, str]:
    """
    Find the best combination of variants for all surfaces, respecting each surface's path prefix.
    For each surface, only consider variants that match the provided path (category, material_type, subtype, variant).
    """
    from itertools import product

    surfaces = area_map.get('surfaces', {})
    if not surfaces:
        return None, "Không có hạng mục nào để báo giá."

    # For each surface, get all matching variant paths
    surface_variants = {}
    for position, surface in surfaces.items():
        path_prefix = surface.get('path', [])
        # Nếu user cung cấp đến variant (tức là path trỏ đến node có 'Vật tư'), chỉ lấy đúng path đó
        node = data
        is_variant = False
        for part in path_prefix:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        if node and isinstance(node, dict) and 'Vật tư' in node:
            # Đã đến variant cụ thể
            surface_variants[position] = [path_prefix]
            continue
        # Nếu chưa đến variant, vét cạn các variant path bắt đầu bằng path_prefix
        all_variants = get_all_variant_paths(data)
        matching_variants = [p for p in all_variants if p[:len(path_prefix)] == path_prefix]
        if not matching_variants:
            return None, f"Không tìm thấy vật liệu phù hợp cho hạng mục '{position}' với path {path_prefix}"
        surface_variants[position] = matching_variants

    # Sinh tất cả tổ hợp variant cho các surfaces
    all_positions = list(surface_variants.keys())
    all_variant_lists = [surface_variants[pos] for pos in all_positions]
    best_combo = None
    best_cost = float('inf')
    best_details = {}
    best_diff = float('inf')

    for combo in product(*all_variant_lists):
        total_cost = 0
        details = {}
        for idx, variant_path in enumerate(combo):
            position = all_positions[idx]
            surface = surfaces[position]
            area = float(surface.get('area', 0))
            variant_info = get_variant_info(data, variant_path)
            if not variant_info:
                total_cost = float('inf')
                break
            unit_vt = variant_info['unit_vattu']
            unit_nc = variant_info['unit_nhancong']
            surface_cost = (unit_vt + unit_nc) * area
            total_cost += surface_cost
            details[position] = {
                'path': ' > '.join(variant_path),
                'area': area,
                'unit_vattu': unit_vt,
                'unit_nhancong': unit_nc,
                'total_cost': surface_cost,
                'type': 'specific'
            }
        if total_cost == float('inf'):
            continue
        diff = abs(total_cost - budget)
        if total_cost <= budget and diff < best_diff:
            best_combo = combo
            best_cost = total_cost
            best_details = details
            best_diff = diff
        elif total_cost > budget and best_combo is None:
            if diff < best_diff:
                best_combo = combo
                best_cost = total_cost
                best_details = details
                best_diff = diff

    if not best_details:
        return None, "Không tìm được phương án phù hợp với ngân sách."

    result = {
        "results": best_details,
        "summary": {
            "total_budget": budget,
            "total_cost_min": best_cost,
            "total_cost_max": best_cost
        }
    }
    if best_cost <= budget:
        result["summary"]["status"] = "Tổng chi phí NẰM TRONG ngân sách."
    else:
        result["summary"]["status"] = "Tổng chi phí VƯỢT ngân sách."
    return result, "Thành công"
