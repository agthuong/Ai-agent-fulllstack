import streamlit as st
import asyncio
import base64
import json
import uuid
import os
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from src.react_agent.graph import graph
from src.react_agent.vision import get_gemini_vision_report
from src.react_agent.prompts import VISION_PROMPT
from src.react_agent.state import State

# --- Page Configuration ---
st.set_page_config(
    page_title="DBPlus Quoting Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Constants & Paths ---
SESSION_HISTORY_PATH = './chat_sessions/'
UPLOADS_PATH = './uploads/'
os.makedirs(SESSION_HISTORY_PATH, exist_ok=True)
os.makedirs(UPLOADS_PATH, exist_ok=True)

# Node names for visualization
NODE_ORDER = ['history_summarizer', 'strategist_router', 'executor_agent', 'final_responder']
NODE_MAPPING = {
    'history_summarizer': 'B',
    'strategist_router': 'C',
    'executor_agent': 'D',
    'final_responder': 'E'
}

# --- Session State Management ---
def initialize_session():
    """Initializes a new chat session state."""
    session_id = str(uuid.uuid4())
    st.session_state.clear()
    st.session_state.session_id = session_id
    st.session_state.messages = []
    st.session_state.graph_state = {'nodes': {}, 'status': 'idle'}
    st.query_params["session_id"] = session_id
    # Ensure a file is created for the new session to appear in the list
    save_session_history(session_id, [])

def load_session(session_id):
    """Loads a specific chat session into the state."""
    st.session_state.session_id = session_id
    st.session_state.messages = load_session_history(session_id)
    st.session_state.graph_state = {'nodes': {}, 'status': 'idle'}


# --- File & History I/O ---
def save_session_history(session_id, history):
    with open(os.path.join(SESSION_HISTORY_PATH, f"{session_id}.json"), 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_session_history(session_id):
    history_file = os.path.join(SESSION_HISTORY_PATH, f"{session_id}.json")
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

# --- Visualization ---
def get_graph_visualization(graph_state):
    """Generates the Mermaid diagram string based on the current graph state."""
    graph_definition = """
        graph TD
            A[Start] --> B(History Summarizer);
            B --> C{Strategist Router};
            C --> D[Executor Agent];
            C --> E[Final Responder];
            D --> E;
            E --> F[End];
            classDef default fill:#2d2d2d,stroke:#888,color:#ddd;
            classDef running fill:#e67e22,stroke:#d35400,color:#fff;
            classDef completed fill:#2ecc71,stroke:#27ae60,color:#fff;
    """
    if graph_state['status'] == 'running':
        graph_definition += "\nclass A running;"

    for node_name, info in graph_state['nodes'].items():
        node_id = NODE_MAPPING.get(node_name)
        if node_id and info['status'] == 'completed':
            graph_definition += f"\nclass {node_id} completed;"

    if graph_state['status'] == 'finished':
        graph_definition += "\nclass F completed;"

    return graph_definition


# --- Main App Logic ---
async def main():
    st.title("DBPlus Quoting Assistant")

    # --- Sidebar for Session Management ---
    with st.sidebar:
        st.header("Chat Sessions")
        if st.button("New Chat", use_container_width=True, type="primary"):
            initialize_session()
            st.rerun()

        # List existing sessions
        sessions = [f[:-5] for f in os.listdir(SESSION_HISTORY_PATH) if f.endswith(".json")]
        sorted_sessions = sorted(sessions, key=lambda s: os.path.getmtime(os.path.join(SESSION_HISTORY_PATH, f"{s}.json")), reverse=True)
        
        for session_id in sorted_sessions:
            history = load_session_history(session_id)
            title = history[0]['content'][:30] if history and history[0]['type'] == 'human' else 'New Chat'
            if st.button(title, key=session_id, use_container_width=True):
                load_session(session_id)
                st.rerun()
        
        st.header("Upload Image")
        uploaded_file = st.file_uploader("Upload an image for analysis", type=["jpg", "jpeg", "png"])


    # Initialize session if not present from sidebar selection
    if 'session_id' not in st.session_state:
        initialize_session()

    # --- Main Chat and Visualization Area ---
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Chat")
        chat_container = st.container(height=600, border=True)
        with chat_container:
            for msg in st.session_state.messages:
                with st.chat_message(msg["type"]):
                    if msg.get("image_path"):
                        st.image(msg["image_path"], width=200)
                    st.markdown(msg["content"])
    
    with col2:
        st.subheader("Processing Flow")
        graph_placeholder = st.empty()
        details_placeholder = st.container(height=450, border=True)

    # --- Handle Image Upload ---
    if uploaded_file and 'processed_image' not in st.session_state:
        st.session_state.processed_image = True # Prevent reprocessing on rerun
        
        # Save temp file
        temp_image_path = os.path.join(UPLOADS_PATH, f"{st.session_state.session_id}_{uploaded_file.name}")
        with open(temp_image_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Call vision API
        with st.spinner("Analyzing image..."):
            image_report = await get_gemini_vision_report(temp_image_path, prompt=VISION_PROMPT)
            
        # Add messages to history
        with chat_container:
            with st.chat_message("human"):
                st.image(temp_image_path, width=200)
                st.markdown("Image uploaded for analysis.")
        
        st.session_state.messages.append({"type": "human", "content": "Image uploaded for analysis.", "image_path": temp_image_path})
        
        with chat_container:
             with st.chat_message("system"):
                st.markdown(f"**[Image Analysis Report]**\n\n{image_report}")

        st.session_state.messages.append({"type": "system", "content": f"**[Image Analysis Report]**\n\n{image_report}"})
        save_session_history(st.session_state.session_id, st.session_state.messages)


    # --- Handle Chat Input ---
    if prompt := st.chat_input("Ask a question..."):
        st.session_state.processed_image = False # Reset for next upload
        
        with chat_container:
            with st.chat_message("human"):
                st.markdown(prompt)
        st.session_state.messages.append({"type": "human", "content": prompt})
        
        # Reset graph state for this run
        st.session_state.graph_state = {'nodes': {}, 'status': 'running'}
        
        # Convert messages for the graph
        messages_for_graph = [AIMessage(**msg) if msg['type'] == 'ai' else HumanMessage(**msg) if msg['type'] == 'human' else SystemMessage(**msg) for msg in st.session_state.messages]
        initial_state = State(messages=messages_for_graph)

        # Stream graph execution
        async for chunk in graph.astream_log(initial_state, include_types=["llm"]):
            for op in chunk.ops:
                path = op['path']
                if path.startswith("/logs/") and "streamed_output" in op['value']:
                    # It's a node that has finished
                    node_name = path.split('/')[2]
                    if node_name in NODE_MAPPING:
                        # Get final output of the node
                        final_output = op['value']['final_output']
                        
                        # Update state
                        st.session_state.graph_state['nodes'][node_name] = {
                            'status': 'completed',
                            'input': op['value']['input'],
                            'output': final_output
                        }

                        # Update UI in real-time
                        graph_placeholder.mermaid(get_graph_visualization(st.session_state.graph_state))
                        with details_placeholder:
                            with st.expander(f"Node: {node_name}", expanded=True):
                                st.write("**Input:**")
                                st.json(op['value']['input'], expanded=False)
                                st.write("**Output:**")
                                st.json(final_output, expanded=True)

        st.session_state.graph_state['status'] = 'finished'
        graph_placeholder.mermaid(get_graph_visualization(st.session_state.graph_state))
        
        # Display final response
        final_messages = st.session_state.graph_state.get('nodes', {}).get('final_responder', {}).get('output', {}).get('messages', [])
        if final_messages:
            assistant_response = final_messages[-1].content
            with chat_container:
                with st.chat_message("ai"):
                    st.markdown(assistant_response)
            st.session_state.messages.append({"type": "ai", "content": assistant_response})
        
        save_session_history(st.session_state.session_id, st.session_state.messages)
        st.rerun()


if __name__ == "__main__":
    # If a session_id is in the query params, load it.
    if 'session_id' in st.query_params and 'session_id' not in st.session_state:
        load_session(st.query_params['session_id'])

    asyncio.run(main()) 