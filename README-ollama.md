# Using Ollama with ReAct Agent

This document explains how to set up and use Ollama with the ReAct Agent.

## Setup

1. Install Ollama by following the instructions on [the Ollama website](https://ollama.ai/).

2. Pull the model you want to use, for example:
   ```bash
   ollama pull qwen3:30b
   ```

3. Make sure you have installed the project with Ollama support:
   ```bash
   pip install -e .
   ```

## Configuration

The project has been configured to use Ollama by default with the `qwen3:30b-a3b` model. You can change this in two ways:

1. **Modify the default in the code**: Edit `src/react_agent/configuration.py` to change the default model.

2. **Override at runtime**: When using the agent, provide a configuration with your desired model.

## Examples

### Direct Use of Ollama

```python
from langchain_ollama import ChatOllama

# Initialize the Ollama model
llm = ChatOllama(model="qwen3:30b-a3b")

# Invoke the model with a message
response = llm.invoke([("human", "Hello")])
print(response.content)
```

### Using Ollama with the ReAct Agent

The agent can be used in both synchronous and asynchronous ways:

#### Synchronous Usage

```python
from react_agent.graph import graph

# Invoke the agent synchronously
response = graph.invoke(
    {"messages": [{"role": "user", "content": "What is the capital of France?"}]},
    {"configurable": {"model": "ollama/qwen3:30b-a3b"}}
)

# Print the final response
final_message = response["messages"][-1]
print(final_message.content)
```

#### Asynchronous Usage

```python
import asyncio
from react_agent.graph import graph

async def run_agent():
    # Invoke the agent asynchronously
    response = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "What is the capital of France?"}]},
        {"configurable": {"model": "ollama/qwen3:30b-a3b"}}
    )

    # Print the final response
    final_message = response["messages"][-1]
    print(final_message.content)

# Run the async function
if __name__ == "__main__":
    asyncio.run(run_agent())
```

## Troubleshooting

- **Model Not Found**: If you get a "model not found" error, make sure you've pulled the model using `ollama pull [model-name]`.
- **Connection Error**: Ensure the Ollama service is running by checking `http://localhost:11434/` in your browser.
- **Async/Sync Error**: If you get a `TypeError: No synchronous function provided` error, make sure you're using the correct API - `invoke` for synchronous calls and `ainvoke` for asynchronous calls.
- **Performance**: For better performance with large models, ensure your machine meets the recommended system requirements for the model you're using.

## Supported Models

The integration has been tested with the following Ollama models:
- qwen3:30b-a3b
- llama3

You can use any model available in Ollama that supports chat completion. 