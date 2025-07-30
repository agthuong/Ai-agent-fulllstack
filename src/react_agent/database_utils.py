"""Utility functions for working with the new DatabaseNoiThat.json structure."""

import json
import os
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

# Load the database once at module level
_current_dir = os.path.dirname(os.path.abspath(__file__))
_data_dir = os.path.join(_current_dir, '..', '..', 'data')
_database_path = os.path.join(_data_dir, 'DatabaseNoiThat.json')

with open(_database_path, 'r', encoding='utf-8') as f:
    DATABASE = json.load(f)

def get_all_categories() -> List[str]:
    """Get all top-level categories from the database."""
    return list(DATABASE.keys())

def get_material_types(category: str) -> List[str]:
    """Get all material types for a given category."""
    return list(DATABASE.get(category, {}).keys())

def get_material_subtypes(category: str, material_type: str) -> List[str]:
    """Get all subtypes for a given category and material type."""
    return list(DATABASE.get(category, {}).get(material_type, {}).keys())

def get_material_variants(category: str, material_type: str, subtype: str) -> List[str]:
    """Get all variants for a given category, material type, and subtype."""
    return list(DATABASE.get(category, {}).get(material_type, {}).get(subtype, {}).keys())

def get_material_price(category: str, material_type: str, subtype: str, variant: str, cost_type: str = "combined") -> Optional[float]:
    """Get the price for a specific material variant."""
    material_data = DATABASE.get(category, {}).get(material_type, {}).get(subtype, {}).get(variant, {})
    
    if not material_data:
        return None
    
    if cost_type == "material":
        return material_data.get("Vật tư")
    elif cost_type == "labor":
        return material_data.get("Nhân công")
    else:  # combined
        material_cost = material_data.get("Vật tư", 0)
        labor_cost = material_data.get("Nhân công", 0)
        return material_cost + labor_cost

def search_materials(query: str) -> List[Dict[str, Any]]:
    """Search for materials by name across all categories."""
    results = []
    query_lower = query.lower()
    
    for category, category_data in DATABASE.items():
        for material_type, type_data in category_data.items():
            for subtype, subtype_data in type_data.items():
                for variant, variant_data in subtype_data.items():
                    if query_lower in variant.lower() or query_lower in subtype.lower():
                        material_info = {
                            "category": category,
                            "material_type": material_type,
                            "subtype": subtype,
                            "variant": variant,
                            "material_cost": variant_data.get("Vật tư"),
                            "labor_cost": variant_data.get("Nhân công"),
                            "combined_cost": (variant_data.get("Vật tư", 0) + variant_data.get("Nhân công", 0))
                        }
                        results.append(material_info)
    
    return results

def get_price_range(category: str, material_type: str, subtype: str = None) -> dict:
    """Get the price ranges for material and labor costs for a given category, material type, and optional subtype."""
    result = {
        "material_min": None,
        "material_max": None,
        "labor_min": None,
        "labor_max": None,
        "combined_min": None,
        "combined_max": None
    }
    
    # Collect all prices
    material_prices = []
    labor_prices = []
    combined_prices = []
    
    # If subtype is provided, get price range for that specific subtype
    if subtype is not None:
        subtype_data = DATABASE.get(category, {}).get(material_type, {}).get(subtype, {})
        
        if not subtype_data:
            return result
        
        for variant_data in subtype_data.values():
            material_cost = variant_data.get("Vật tư")
            labor_cost = variant_data.get("Nhân công")
            
            if material_cost is not None:
                material_prices.append(material_cost)
            if labor_cost is not None:
                labor_prices.append(labor_cost)
            if material_cost is not None or labor_cost is not None:
                combined_cost = (material_cost or 0) + (labor_cost or 0)
                combined_prices.append(combined_cost)
    else:
        # If no subtype is provided, get price range for all subtypes under the category and material_type
        material_type_data = DATABASE.get(category, {}).get(material_type, {})
        
        if not material_type_data:
            return result
        
        for subtype_data in material_type_data.values():
            for variant_data in subtype_data.values():
                material_cost = variant_data.get("Vật tư")
                labor_cost = variant_data.get("Nhân công")
                
                if material_cost is not None:
                    material_prices.append(material_cost)
                if labor_cost is not None:
                    labor_prices.append(labor_cost)
                if material_cost is not None or labor_cost is not None:
                    combined_cost = (material_cost or 0) + (labor_cost or 0)
                    combined_prices.append(combined_cost)
    
    # Set the results
    if material_prices:
        result["material_min"] = min(material_prices)
        result["material_max"] = max(material_prices)
    
    if labor_prices:
        result["labor_min"] = min(labor_prices)
        result["labor_max"] = max(labor_prices)
    
    if combined_prices:
        result["combined_min"] = min(combined_prices)
        result["combined_max"] = max(combined_prices)
    
    return result
