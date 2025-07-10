"""Example demonstrating the material price query tool."""

import asyncio
from react_agent.graph import graph
from react_agent.configuration import Configuration
from react_agent.tools import material_price_query


async def query_material_prices():
    """Query material prices using the ReAct agent with Ollama."""
    # Sample queries to test the material price tool
    queries = [
        "What is the price of wood?",
        "Giá của đá là bao nhiêu?",  # Price of stone
        "Tell me about paint prices",
        "Giấy dán tường có giá thế nào?",  # What's the price of wallpaper?
    ]
    
    for query in queries:
        print(f"\n--- Query: {query} ---")
        # Use the graph with Ollama model to process the query
        response = await graph.ainvoke(
            {"messages": [{"role": "user", "content": query}]},
            {"configurable": {"model": "ollama/qwen3:30b-a3b"}}
        )
        
        # Print the final response from the agent
        final_message = response["messages"][-1]
        print("Agent Response:", final_message.content)


# Direct testing of the material_price_query tool
async def test_direct_tool_usage():
    """Test the material_price_query tool directly without using the agent."""
    print("\n--- Direct Tool Testing ---")
    
    # Test each material type
    material_types = ["wood", "stone", "paint", "wallpaper"]
    
    for material in material_types:
        print(f"\nPrices for {material}:")
        result = await material_price_query(material_type=material)
        
        if "results" in result:
            for item in result["results"]:
                print(f"- {item}")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
    
    # Test with invalid material type
    result = await material_price_query(material_type="cement")
    print("\nTest with invalid material type:")
    print(f"Error: {result.get('error', 'Unknown error')}")


async def main():
    print("Testing simplified material price query tool...")
    
    # First test the tool directly
    await test_direct_tool_usage()
    
    # Then test through the agent interface
    print("\n\nTesting through the agent interface...")
    await query_material_prices()


if __name__ == "__main__":
    asyncio.run(main()) 