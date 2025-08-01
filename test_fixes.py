#!/usr/bin/env python3
"""Test script to verify the fixes for parameter mapping and tool selection."""

import sys
import os
import asyncio
import json

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from react_agent.agents.strategist import strategist_node
from react_agent.agents.executor import executor_node

async def test_strategist_tool_selection():
    """Test strategist tool selection logic."""
    print("=== Testing Strategist Tool Selection ===")
    
    # Test case 1: Budget + Area_map exists -> should use propose_options_for_budget
    test_case_1 = {
        "messages": [],
        "history_summary": json.dumps({
            "events_summary": [
                "User provided room photo with dimensions 30m2 for floor and ceiling, 20m2 for each wall",
                "System identified wooden floor, stone-like wall panels, and gypsum ceiling from image"
            ],
            "budget": 300000000,
            "area_map": [
                {
                    "position": "sàn",
                    "category": "Sàn",
                    "material_type": "Sàn gỗ",
                    "area": 30.00
                },
                {
                    "position": "trần",
                    "category": "Trần", 
                    "material_type": "Trần thạch cao",
                    "area": 30.00
                }
            ]
        }, ensure_ascii=False),
        "user_input": "Cho tôi báo giá thi công như hình"
    }
    
    result_1 = await strategist_node(test_case_1)
    print("Test Case 1 (Budget + Area_map):")
    print(f"Plan: {result_1.get('plan', [])}")
    print(f"Should use propose_options_for_budget: {'propose_options_for_budget' in str(result_1.get('plan', []))}")
    print()
    
    # Test case 2: Area_map only (no budget) -> should use get_material_price_ranges
    test_case_2 = {
        "messages": [],
        "history_summary": json.dumps({
            "events_summary": [
                "User provided room photo with dimensions 30m2 for floor and ceiling",
                "System identified wooden floor and gypsum ceiling from image"
            ],
            "budget": None,
            "area_map": [
                {
                    "position": "sàn",
                    "category": "Sàn",
                    "material_type": "Sàn gỗ",
                    "area": 30.00
                }
            ]
        }, ensure_ascii=False),
        "user_input": "Cho tôi khoảng giá vật liệu này"
    }
    
    result_2 = await strategist_node(test_case_2)
    print("Test Case 2 (Area_map only, no budget):")
    print(f"Plan: {result_2.get('plan', [])}")
    print(f"Should use get_material_price_ranges: {'get_material_price_ranges' in str(result_2.get('plan', []))}")
    print()
    
    # Test case 3: Simple material search
    test_case_3 = {
        "messages": [],
        "history_summary": json.dumps({
            "events_summary": [],
            "budget": None,
            "area_map": []
        }, ensure_ascii=False),
        "user_input": "Tìm vật liệu gỗ"
    }
    
    result_3 = await strategist_node(test_case_3)
    print("Test Case 3 (Material search):")
    print(f"Plan: {result_3.get('plan', [])}")
    print(f"Should use search_materials_new: {'search_materials_new' in str(result_3.get('plan', []))}")
    print()

async def test_executor_parameter_mapping():
    """Test executor parameter mapping."""
    print("=== Testing Executor Parameter Mapping ===")
    
    # Test Vietnamese parameter mapping
    test_subtask = "Step 1: Propose material options suitable for budget 300 million for surfaces: sàn (Sàn - Sàn gỗ, 30m²), trần (Trần - Trần thạch cao, 30m²)"
    
    test_state = {
        "messages": [],
        "plan": [test_subtask],
        "current_step": 0,
        "tool_results": [],
        "execution_summary": ""
    }
    
    result = await executor_node(test_state)
    print("Test Subtask:", test_subtask)
    print("Tool Results:")
    for tool_result in result.get('tool_results', []):
        if isinstance(tool_result, dict):
            print(f"  Tool: {tool_result.get('tool_name', 'Unknown')}")
            print(f"  Args: {tool_result.get('tool_args', {})}")
            # Check if Vietnamese parameters are used
            args = tool_result.get('tool_args', {})
            if 'surfaces' in args:
                for surface in args['surfaces']:
                    category = surface.get('category', '')
                    material_type = surface.get('material_type', '')
                    print(f"    Category: {category} (Vietnamese: {'Sàn' in category or 'Trần' in category or 'Tường' in category})")
                    print(f"    Material Type: {material_type} (Vietnamese: {'Sàn' in material_type or 'Trần' in material_type})")
    print()

async def main():
    """Run all tests."""
    try:
        await test_strategist_tool_selection()
        await test_executor_parameter_mapping()
        print("=== All Tests Completed ===")
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())