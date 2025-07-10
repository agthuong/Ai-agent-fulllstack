"""Module for managing conversation history."""
from collections import deque, defaultdict
from typing import Dict, List, Deque, Any, Optional
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
import threading

class MemoryManager:
    """A singleton class to manage conversation histories."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):  # Ensure __init__ runs only once
            self.histories = defaultdict(list)
            self.image_contexts = defaultdict(dict) # To store image_base64 and report
            self.max_history_length = 50
            self.initialized = True

    def get_history(self, conversation_id: str) -> List[BaseMessage]:
        """
        Retrieves the message history for a given conversation.

        Args:
            conversation_id: The unique identifier for the conversation.

        Returns:
            A list of messages for the conversation.
        """
        return self.histories.get(conversation_id, [])

    def add_messages(self, conversation_id: str, messages: List[BaseMessage]):
        """
        Adds new messages to the conversation history and prunes it.

        Args:
            conversation_id: The unique identifier for the conversation.
            messages: A list of new messages to add.
        """
        self.histories[conversation_id].extend(messages)
        # Trim history to the maximum length
        self.histories[conversation_id] = self.histories[conversation_id][-self.max_history_length:]

    def add_image_context(self, conversation_id: str, image_base64: str, report: str):
        """Stores image-related context for a conversation."""
        self.image_contexts[conversation_id] = {
            "image_base64": image_base64,
            "report": report
        }

    def get_image_context(self, conversation_id: str) -> Optional[Dict[str, str]]:
        """Retrieves image-related context for a conversation."""
        return self.image_contexts.get(conversation_id)

    def clear_history(self, conversation_id: str):
        """
        Clears the history for a specific conversation.

        Args:
            conversation_id: The unique identifier for the conversation.
        """
        if conversation_id in self.histories:
            del self.histories[conversation_id]
        if conversation_id in self.image_contexts:
            del self.image_contexts[conversation_id]
            
    def list_sessions(self) -> List[str]:
        """Returns a list of all active session IDs."""
        return list(self.histories.keys())

    def get_history_serializable(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Returns a serializable version of the history for a given session."""
        serializable_history = []
        history = self.get_history(conversation_id)
        
        for msg in history:
            msg_dict = msg.dict()
            
            # If it's a HumanMessage that introduced an image, add the image URL
            if isinstance(msg, HumanMessage):
                image_context = self.get_image_context(conversation_id)
                
                # FIX: Check for image_context and report existence before proceeding.
                # Also ensure msg.content is a string before using 'in'.
                if image_context and "report" in image_context:
                    report = image_context["report"]
                    if isinstance(msg.content, str) and report in msg.content:
                        # Safely get image_base64, now that we know image_context is valid
                        image_base64 = image_context.get("image_base64", "")
                        msg_dict['content_parts'] = [
                            {'type': 'text', 'text': msg.content},
                            {
                                'type': 'image_url',
                                'image_url': {
                                    'url': f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]

            serializable_history.append(msg_dict)
            
        return serializable_history

# Singleton instance of the memory manager
memory_manager = MemoryManager() 