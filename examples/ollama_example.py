"""Example using Ollama with the ReAct agent."""

import asyncio
from langchain_ollama import ChatOllama
from react_agent.graph import graph
from react_agent.configuration import Configuration

# Example 1: Direct use of Ollama
def direct_ollama_example():
    """Demonstrate direct use of Ollama without the agent."""
    llm = ChatOllama(model="qwen3:30b-a3b")
    response = llm.invoke([("human", "Hello")])
    print("Direct Ollama Response:", response.content)

# Example 2: Using Ollama with the ReAct agent (synchronous)
def agent_ollama_example_sync():
    """Demonstrate using Ollama with the ReAct agent synchronously."""
    # You can use the graph with this configuration
    response = graph.invoke(
        {"messages": [{"role": "user", "content": "What is the capital of France?"}]},
        {"configurable": {"model": "ollama/qwen3:30b-a3b"}}
    )
    
    # Print the final response from the agent
    final_message = response["messages"][-1]
    print("Agent Response (Sync):", final_message.content)

# Example 3: Using Ollama with the ReAct agent (asynchronous)
async def agent_ollama_example_async():
    """Demonstrate using Ollama with the ReAct agent asynchronously."""
    # You can use the graph with this configuration
    response = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "What is the population of Japan?"}]},
        {"configurable": {"model": "ollama/qwen3:30b-a3b"}}
    )
    
    # Print the final response from the agent
    final_message = response["messages"][-1]
    print("Agent Response (Async):", final_message.content)

async def main():
    print("Running direct Ollama example...")
    direct_ollama_example()
    
    print("\nRunning Ollama with ReAct agent (synchronous)...")
    agent_ollama_example_sync()
    
    print("\nRunning Ollama with ReAct agent (asynchronous)...")
    await agent_ollama_example_async()

if __name__ == "__main__":
    asyncio.run(main()) 