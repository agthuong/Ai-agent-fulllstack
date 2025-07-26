"""
Memory manager for the simplified agent.
"""
import json
import os
from typing import Dict, Any, List, Optional, Union

class MemoryManager:
    """
    Simple memory manager to store and retrieve user-specific memories.
    """
    def __init__(self, storage_dir: str = "user_memories"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        
    def save_memory(self, session_id: str, key: str, value: Dict[str, Any]) -> None:
        """Save a memory value for a specific session and key."""
        file_path = os.path.join(self.storage_dir, f"{session_id}.json")
        
        try:
            # Load existing memories or create new dict
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    memories = json.load(f)
            else:
                memories = {}
                
            # Update the specific key
            memories[key] = value
            
            # Save back to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(memories, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving memory: {e}")
    
    def get_memory(self, session_id: str, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a memory value for a specific session and key."""
        file_path = os.path.join(self.storage_dir, f"{session_id}.json")
        
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    memories = json.load(f)
                return memories.get(key)
            return None
        except Exception as e:
            print(f"Error retrieving memory: {e}")
            return None

    def get_all_memories(self, session_id: str) -> Dict[str, Any]:
        """Get all memories for a session."""
        file_path = os.path.join(self.storage_dir, f"{session_id}.json")
        
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Error retrieving all memories: {e}")
            return {}

class QuoteMemory:
    """
    Specialized memory manager for storing and retrieving quote parameters.
    """
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self.memory_key = "quote_params"
    
    def save_quote_params(self, session_id: str, params: Dict[str, Any]) -> None:
        """
        Save quote parameters to memory.
        
        Args:
            session_id: User session identifier
            params: Dictionary of quote parameters (material_type, type, area_map, budget, etc.)
        """
        # Filter out None values and empty containers
        cleaned_params = {k: v for k, v in params.items() 
                         if v is not None and (not isinstance(v, (dict, list)) or len(v) > 0)}
        
        # Store timestamp for freshness
        cleaned_params["timestamp"] = self._get_timestamp()
        
        self.memory_manager.save_memory(session_id, self.memory_key, cleaned_params)
    
    def get_quote_params(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve stored quote parameters.
        
        Args:
            session_id: User session identifier
            
        Returns:
            Dictionary of stored parameters or None if not found
        """
        params = self.memory_manager.get_memory(session_id, self.memory_key)
        if params and "timestamp" in params:
            # Remove internal timestamp before returning
            params = params.copy()
            params.pop("timestamp")
        return params
    
    def update_quote_params(self, session_id: str, new_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update stored parameters with new values.
        
        Args:
            session_id: User session identifier
            new_params: New parameters to update
            
        Returns:
            Updated parameters dictionary
        """
        current_params = self.get_quote_params(session_id) or {}
        
        # Special handling for area_map to merge instead of replace
        if "area_map" in new_params and "area_map" in current_params:
            merged_area_map = current_params["area_map"].copy()
            merged_area_map.update(new_params["area_map"])
            new_params["area_map"] = merged_area_map
        
        # Update current params with new ones
        current_params.update(new_params)
        
        # Save updated params
        self.save_quote_params(session_id, current_params)
        
        return current_params
    
    def format_for_prompt(self, session_id: str) -> str:
        """
        Format stored parameters for inclusion in prompt.
        
        Args:
            session_id: User session identifier
            
        Returns:
            String representation of parameters for prompt
        """
        params = self.get_quote_params(session_id)
        if not params:
            return "No previous quote parameters stored."
        
        # Format for prompt
        lines = ["Previous quote parameters:"]
        
        for key, value in params.items():
            if key == "area_map" and isinstance(value, dict):
                lines.append(f"- {key}:")
                for material, details in value.items():
                    if isinstance(details, dict):
                        area = details.get("area", "N/A")
                        material_type = details.get("type", "unspecified type")
                        lines.append(f"  * {material} ({material_type}): {area}")
                    else:
                        lines.append(f"  * {material}: {details}")
            else:
                lines.append(f"- {key}: {value}")
        
        return "\n".join(lines)
    
    def _get_timestamp(self) -> int:
        """Get current timestamp."""
        import time
        return int(time.time())

# Create singleton instances
memory_manager = MemoryManager()
quote_memory = QuoteMemory(memory_manager) 