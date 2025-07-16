import asyncio
from typing import Optional
import sys
import os

# Add the project root to the Python path to resolve the ModuleNotFoundError
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Make sure the tool is importable.
# This assumes you are running from the root of the project.
from src.react_agent.tools import material_price_query

async def run_test(
    material_type: str, 
    type: Optional[str] = None, 
    mode: str = 'range'
):
    """Helper function to run a single test and print the output."""
    print("="*80)
    print(f"🚀 TESTING: material_type='{material_type}', type='{type}', mode='{mode}'")
    print("-"*80)
    
    try:
        # The @tool decorator modifies the function to accept a single dict argument
        tool_input = {
            "material_type": material_type,
            "mode": mode
        }
        if type is not None:
            tool_input["type"] = type
            
        result = await material_price_query.ainvoke(tool_input)
        print("✅ RESULT:")
        print(result)
    except Exception as e:
        print(f"🔥 ERROR: {e}")
    
    print("="*80)
    print("\n")


async def main():
    """Main function to run all test cases."""
    
    print("========= STARTING TOOL TESTS =========\n")

    # --- Case 1: Range mode with a specific, valid type ---
    # Should return the price range for Marble only.
    await run_test(material_type="stone", type="Marble", mode="range")

    # --- Case 2: Range mode with a null type ---
    # Should return the price range for ALL wood types.
    await run_test(material_type="wood", type=None, mode="range")
    
    # --- Case 3: Range mode with an invalid type ---
    # Should return the range for the entire 'paint' category, with a warning.
    await run_test(material_type="paint", type="invalid_paint_type", mode="range")

    # --- Case 4: Full list mode with a specific, valid type ---
    # Should return a detailed list of ONLY Oak variants.
    await run_test(material_type="wood", type="Oak", mode="full_list")
    
    # --- Case 5: Full list mode with a null type ---
    # Should list ALL stone variants.
    await run_test(material_type="stone", type=None, mode="full_list")

    # --- Case 6: Invalid material_type to test error handling ---
    await run_test(material_type="metal", type=None, mode="range")
    
    print("========= ALL TESTS COMPLETED =========\n")


if __name__ == "__main__":
    # To run this file, execute `python -m examples.test_tool` from the project root.
    asyncio.run(main()) 