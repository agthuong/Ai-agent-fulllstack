"""
Examples demonstrating how to use the unified quote_materials tool in various scenarios.
This file serves both as documentation and as a test case for the tool.
"""

import asyncio
from pprint import pprint
from react_agent.tools import quote_materials
from react_agent.configuration import Configuration
from react_agent.graph import graph

# Sample image report content (simulated)
SAMPLE_IMAGE_REPORT = """
[Image Analysis Report]:
Phân tích hình ảnh phòng khách:

Danh sách vật liệu:
Material: gỗ - Type: Oak - Position: sàn - InStock: true
Material: gỗ - Type: null - Position: tường đối diện - InStock: only_material
Material: gạch - Type: Gạch thẻ - Position: tường trái - InStock: false
Material: sơn - Type: Color paint - Position: tường phải (phán đoán) - InStock: true
Material: sơn - Type: Color paint - Position: tường sau lưng (phán đoán) - InStock: true
Material: sơn - Type: Color paint - Position: trần (phán đoán) - InStock: true

Kết luận: Phòng khách sử dụng sàn gỗ Oak, tường đối diện ốp gỗ, tường trái ốp gạch thẻ, tường phải và sau lưng cùng trần nhà sơn màu.
"""

# Sample material list for multi-component quoting without image
SAMPLE_MATERIAL_LIST = [
    {
        "material": "gỗ",
        "type": "Oak",
        "position": "sàn",
        "in_stock": True
    },
    {
        "material": "sơn",
        "type": "Color paint",
        "position": "tường",
        "in_stock": True
    }
]

async def demonstrate_quote_materials_tool():
    """
    Demonstrate how to use the quote_materials tool in various scenarios.
    This helps developers understand how to use the tool and serves as test cases.
    """
    print("\n=== DEMONSTRATING quote_materials TOOL ===")
    
    examples = [
        {
            "name": "1. Simple price query for a specific material",
            "params": {
                "material_type": "gỗ",
                "type": "Oak",
            }
        },
        {
            "name": "2. Detailed price list for a material category",
            "params": {
                "material_type": "sơn",
                "mode": "single_material",
                "sort_by": "quality"
            }
        },
        {
            "name": "3. Material options within budget",
            "params": {
                "material_type": "đá",
                "area": "20m2",
                "budget": "30 triệu",
                "mode": "options"
            }
        },
        {
            "name": "4. Multi-component quote from image report",
            "params": {
                "image_report": SAMPLE_IMAGE_REPORT,
            }
        },
        {
            "name": "5. Area-based quote from image report",
            "params": {
                "image_report": SAMPLE_IMAGE_REPORT,
                "area": "25"
            }
        },
        {
            "name": "6. Budget-constrained quote from image report",
            "params": {
                "image_report": SAMPLE_IMAGE_REPORT,
                "area": "30m2",
                "budget": "100000000",
                "compare_market": True
            }
        },
        {
            "name": "7. Multi-material quote without image",
            "params": {
                "material_list": SAMPLE_MATERIAL_LIST,
                "area": "40"
            }
        }
    ]
    
    for example in examples:
        print(f"\n\n--- {example['name']} ---")
        print(f"Parameters: {example['params']}")
        try:
            result = quote_materials(**example['params'])
            print("Result preview (first 500 chars):")
            print(result[:500] + "..." if len(result) > 500 else result)
        except Exception as e:
            print(f"Error: {e}")

async def test_through_graph():
    """Test the quote_materials tool through the LangGraph workflow."""
    print("\n=== TESTING THROUGH LANGGRAPH ===")
    
    test_cases = [
        "What is the price of oak wood?",
        "Generate a preliminary quote for materials in the image.",
        "Can you give me options for stone flooring with a budget of 50 million for 30m2?",
        "I need a detailed quote for the materials in the image, area is 45m2 with 200 million budget."
    ]
    
    for query in test_cases:
        print(f"\n--- Query: {query} ---")
        try:
            # Configure with test model
            configuration = Configuration(model="ollama/qwen3:7b-q8_0")
            
            # Use the graph to process the query
            response = await graph.ainvoke(
                {"messages": [{"role": "user", "content": query}]},
                {"configurable": configuration}
            )
            
            # Print the final response from the agent
            final_message = response["messages"][-1]
            print(f"Agent response: {final_message.content[:300]}...")
        except Exception as e:
            print(f"Error testing through graph: {e}")

async def main():
    """Main function to run examples."""
    await demonstrate_quote_materials_tool()
    await test_through_graph()

if __name__ == "__main__":
    asyncio.run(main()) 