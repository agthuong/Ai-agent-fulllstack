# ReAct Agent API Demo

This is a simple web API and interface to demonstrate the ReAct Agent with tool usage.

## Setup

1. Install the required packages:
```
pip install -r requirements.txt
```

2. Make sure Ollama is running and you have pulled the required models:
```
ollama pull qwen3:30b-a3b
ollama pull llama3
```

3. Run the application:
```
python app.py
```

4. Open your browser and navigate to:
```
http://localhost:5000
```

## API Endpoints

### 1. Query the Agent
```
POST /api/query
```

**Request Body:**
```json
{
  "query": "What is the price of wood?",
  "model": "ollama/qwen3:30b-a3b"
}
```

**Response:**
```json
{
  "response": "The agent's response text",
  "tool_calls": [
    {
      "tool": "material_price_query",
      "args": {
        "material_type": "wood"
      }
    }
  ]
}
```

### 2. List Available Models
```
GET /api/models
```

**Response:**
```json
[
  {
    "id": "ollama/qwen3:30b-a3b",
    "name": "Qwen3 30B"
  },
  {
    "id": "ollama/llama3",
    "name": "Llama 3"
  }
]
```

## Web Interface

The web interface allows you to:

1. **Select a Model**: Choose between available LLM models
2. **Enter Queries**: Type your questions in English or Vietnamese
3. **View Responses**: See the agent's response
4. **Examine Tool Usage**: View which tools were used and with what parameters
5. **Try Examples**: Click on example queries to quickly test different scenarios

## Example Queries

1. **Material Price Queries**
   - "What is the price of wood?"
   - "Giá đá là bao nhiêu?" (How much does stone cost?)
   - "Tell me about paint prices"
   - "Giá giấy dán tường" (Wallpaper prices)

2. **Comparative Queries**
   - "So sánh giữa gỗ và đá" (Compare wood and stone)
   - "Which is better for flooring, wood or stone?"

3. **General Knowledge Queries**
   - "How to maintain stone surfaces?"
   - "What are the benefits of using wood in construction?"

## Troubleshooting

1. **Model Loading Errors**: Ensure Ollama is running and the models are properly pulled.

2. **API Connection Issues**: Check that the Flask server is running on port 5000.

3. **Empty Responses**: Make sure your query is clear and the model understands what material information you're looking for.

4. **Vietnamese Text Display Issues**: If Vietnamese text appears garbled, ensure your browser supports UTF-8 encoding. 