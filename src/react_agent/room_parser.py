"""Module for parsing room dimensions and calculating per-surface areas."""

import re
from typing import Dict, Any


def parse_room_dimensions(room_size: str) -> Dict[str, float]:
    """
    Parse room dimensions from a string like "5x10x6" (length x width x height).
    
    Args:
        room_size: String in format "LxWxH" where L, W, H are numbers
    
    Returns:
        Dictionary with length, width, height as floats
    """
    # Match patterns like "5x10x6" or "5 x 10 x 6" or "5.5x10.2x6"
    pattern = r'(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)'
    match = re.match(pattern, room_size.strip())
    
    if not match:
        raise ValueError(f"Invalid room size format: {room_size}. Expected format: LxWxH (e.g., 5x10x6)")
    
    length = float(match.group(1))
    width = float(match.group(2))
    height = float(match.group(3))
    
    return {
        "length": length,
        "width": width,
        "height": height
    }


def calculate_surface_areas(dimensions: Dict[str, float]) -> Dict[str, float]:
    """
    Calculate surface areas for a room based on dimensions.
    
    Args:
        dimensions: Dictionary with length, width, height
    
    Returns:
        Dictionary with surface areas (floor, ceiling, walls)
    """
    length = dimensions["length"]
    width = dimensions["width"]
    height = dimensions["height"]
    
    # Floor and ceiling have the same area
    floor_area = length * width
    ceiling_area = floor_area
    
    # Four walls - two pairs with same dimensions
    wall1_area = length * height  # Two walls with this area
    wall2_area = width * height   # Two walls with this area
    
    return {
        "floor": floor_area,
        "ceiling": ceiling_area,
        "wall1": wall1_area,
        "wall2": wall1_area,  # Second wall with same dimensions as wall1
        "wall3": wall2_area,  # Third wall with same dimensions as wall2
        "wall4": wall2_area   # Fourth wall with same dimensions as wall2
    }


def create_area_map_from_room_size(room_size: str) -> Dict[str, Any]:
    """
    Create an area map from room size string for use in quoting tools.
    
    Args:
        room_size: String in format "LxWxH" (e.g., "5x10x6")
    
    Returns:
        Area map dictionary with surfaces and their areas
    """
    # Parse dimensions
    dimensions = parse_room_dimensions(room_size)
    
    # Calculate surface areas
    surface_areas = calculate_surface_areas(dimensions)
    
    # Map to Vietnamese surface names and database paths
    area_map = {
        "surfaces": {
            "sàn": {
                "path": ["Sàn"],
                "area": f"{surface_areas['floor']:.1f}"
            },
            "trần": {
                "path": ["Trần"],
                "area": f"{surface_areas['ceiling']:.1f}"
            },
            "tường 1": {
                "path": ["Tường và vách"],
                "area": f"{surface_areas['wall1']:.1f}"
            },
            "tường 2": {
                "path": ["Tường và vách"],
                "area": f"{surface_areas['wall2']:.1f}"
            },
            "tường 3": {
                "path": ["Tường và vách"],
                "area": f"{surface_areas['wall3']:.1f}"
            },
            "tường 4": {
                "path": ["Tường và vách"],
                "area": f"{surface_areas['wall4']:.1f}"
            }
        }
    }
    
    return area_map


# Example usage
if __name__ == "__main__":
    # Test with example room size
    room_size = "5x10x6"
    area_map = create_area_map_from_room_size(room_size)
    print(f"Room size: {room_size}")
    print("Area map:")
    for surface, data in area_map["surfaces"].items():
        print(f"  {surface}: {data['area']} m²")
