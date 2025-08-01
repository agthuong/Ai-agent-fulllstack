"""Debug utilities for logging API calls and prompts."""

import os
import json
from datetime import datetime
from typing import Any, Dict, Optional

def log_api_call(
    node_name: str,
    prompt: str,
    response: str,
    additional_info: Optional[Dict[str, Any]] = None
) -> str:
    """
    Log API call details to a debug file.
    
    Args:
        node_name: Name of the node making the API call
        prompt: The prompt sent to the API
        response: The response received from the API
        additional_info: Additional information to log
    
    Returns:
        Path to the debug file
    """
    debug_dir = "debug_logs"
    os.makedirs(debug_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include milliseconds
    filename = f"{debug_dir}/api_call_{timestamp}_{node_name}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("=== API CALL DEBUG LOG ===\n")
        f.write(f"Timestamp: {datetime.now()}\n")
        f.write(f"Node: {node_name}\n")
        f.write(f"File: {filename}\n\n")
        
        f.write("=== PROMPT SENT TO API ===\n")
        f.write(prompt)
        f.write("\n\n")
        
        f.write("=== RESPONSE FROM API ===\n")
        f.write(response)
        f.write("\n\n")
        
        if additional_info:
            f.write("=== ADDITIONAL INFO ===\n")
            f.write(json.dumps(additional_info, ensure_ascii=False, indent=2))
            f.write("\n\n")
        
        f.write("=== END DEBUG LOG ===\n")
    
    print(f"API call logged to: {filename}")
    return filename

def log_state_transition(
    from_node: str,
    to_node: str,
    state: Dict[str, Any],
    transition_reason: Optional[str] = None
) -> str:
    """
    Log state transition between nodes.
    
    Args:
        from_node: Name of the source node
        to_node: Name of the destination node
        state: Current state
        transition_reason: Reason for the transition
    
    Returns:
        Path to the debug file
    """
    debug_dir = "debug_logs"
    os.makedirs(debug_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"{debug_dir}/state_transition_{timestamp}_{from_node}_to_{to_node}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("=== STATE TRANSITION DEBUG LOG ===\n")
        f.write(f"Timestamp: {datetime.now()}\n")
        f.write(f"From: {from_node}\n")
        f.write(f"To: {to_node}\n")
        f.write(f"File: {filename}\n\n")
        
        if transition_reason:
            f.write("=== TRANSITION REASON ===\n")
            f.write(transition_reason)
            f.write("\n\n")
        
        f.write("=== STATE CONTENT ===\n")
        # Filter out sensitive or too large data
        filtered_state = {}
        for key, value in state.items():
            if key == 'messages':
                # Only log message types and lengths
                if isinstance(value, list):
                    filtered_state[key] = [
                        {
                            'type': getattr(msg, 'type', 'unknown'),
                            'content_length': len(getattr(msg, 'content', ''))
                        }
                        for msg in value
                    ]
                else:
                    filtered_state[key] = str(type(value))
            elif isinstance(value, str) and len(value) > 1000:
                filtered_state[key] = f"[String with {len(value)} characters]"
            else:
                filtered_state[key] = value
        
        f.write(json.dumps(filtered_state, ensure_ascii=False, indent=2))
        f.write("\n\n")
        
        f.write("=== END DEBUG LOG ===\n")
    
    print(f"State transition logged to: {filename}")
    return filename 