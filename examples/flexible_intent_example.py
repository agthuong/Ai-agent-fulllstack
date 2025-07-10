"""Example demonstrating flexible intent detection with the updated system prompt."""

import asyncio
from react_agent.graph import graph
from react_agent.configuration import Configuration


async def test_flexible_intent():
    """Test the agent's ability to detect intent and use appropriate tools."""
    
    # Sample queries to test different intents
    queries = [
        # Material price queries with varying specificity and language
        "What is the price of wood?",
        "Tôi muốn biết giá đá",
        "Các loại sơn giá bao nhiêu?",
        "Tell me about wallpaper prices",
        
        # Mixed/ambiguous queries
        "I need to paint my house, what options do I have?",
        "Tôi nên dùng đá hay giấy dán tường để trang trí?",
        
        # General knowledge questions
        "What are the benefits of using wood for furniture?",
        "How do I maintain stone countertops?",
    ]
    
    for i, query in enumerate(queries):
        print(f"\n\n======= Query {i+1}: {query} =======")
        
        # Use the graph with the improved system prompt
        response = await graph.ainvoke(
            {"messages": [{"role": "user", "content": query}]},
            {"configurable": {"model": "ollama/qwen3:30b-a3b"}}
        )
        
        # Print the final response from the agent
        final_message = response["messages"][-1]
        print("\nAgent Response:")
        print(final_message.content)
        
        # Brief pause between queries
        if i < len(queries) - 1:
            await asyncio.sleep(1)


async def main():
    print("Testing flexible intent detection with updated system prompt...")
    await test_flexible_intent()


if __name__ == "__main__":
    asyncio.run(main()) 