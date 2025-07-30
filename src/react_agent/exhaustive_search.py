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
    Find the best variant that brings total cost closest to budget.
    
    Args:
        data: Database dictionary
        area_map: Area map with surface areas
        budget: Target budget
    
    Returns:
        Tuple of (result_dict, status_message)
    """
    # Get all variant paths
    variant_paths = get_all_variant_paths(data)
    
    if not variant_paths:
        return None, "Không tìm thấy vật liệu phù hợp trong database"
    
    best_variant = None
    best_cost = float('inf')
    best_details = {}
    best_diff = float('inf')
    
    # Find variant with cost closest to budget
    for path in variant_paths:
        total_cost, surface_details = calculate_total_cost_for_variant(data, area_map, path)
        
        # Skip if calculation failed
        if total_cost == float('inf'):
            continue
        
        # Calculate difference from budget
        diff = abs(total_cost - budget)
        
        # Prefer variants that are under budget, but if all are over, pick the closest
        if total_cost <= budget and diff < best_diff:
            best_variant = path
            best_cost = total_cost
            best_details = surface_details
            best_diff = diff
        elif total_cost > budget and best_variant is None:  # All variants so far are over budget
            if diff < best_diff:
                best_variant = path
                best_cost = total_cost
                best_details = surface_details
                best_diff = diff
    
    if best_variant is None:
        return None, "Không tìm được phương án phù hợp"
    
    # Create result structure
    result = {
        "results": best_details,
        "summary": {
            "total_budget": budget,
            "total_cost_min": best_cost,
            "total_cost_max": best_cost
        }
    }
    
    # Add status
    if best_cost <= budget:
        result["summary"]["status"] = "Tổng chi phí NẰM TRONG ngân sách."
    else:
        result["summary"]["status"] = "Tổng chi phí VƯỢT ngân sách."
    
    return result, "Thành công"
