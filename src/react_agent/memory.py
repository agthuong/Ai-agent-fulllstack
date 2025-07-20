"""Module for managing conversation history."""
import os
import json
import pickle
import time
from collections import deque, defaultdict
from typing import Dict, List, Deque, Any, Optional, Tuple, Set
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
import threading

class MessageSerializer:
    """Helper class to serialize and deserialize langchain messages."""
    
    @staticmethod
    def serialize_message(message: BaseMessage) -> Dict[str, Any]:
        """Serialize a langchain message to a dictionary."""
        result = {
            "type": message.__class__.__name__,
            "content": message.content,
        }
        if hasattr(message, "tool_calls") and getattr(message, "tool_calls", None):
            result["tool_calls"] = getattr(message, "tool_calls")
            
        if hasattr(message, "id") and getattr(message, "id", None):
            result["id"] = getattr(message, "id")
            
        return result
    
    @staticmethod
    def deserialize_message(data: Dict[str, Any]) -> BaseMessage:
        """Deserialize a dictionary to a langchain message."""
        msg_type = data["type"]
        content = data["content"]
        
        if msg_type == "HumanMessage":
            return HumanMessage(content=content)
        elif msg_type == "AIMessage":
            msg = AIMessage(content=content)
            if "tool_calls" in data:
                msg.tool_calls = data["tool_calls"]
            if "id" in data:
                msg.id = data["id"]
            return msg
        elif msg_type == "SystemMessage":
            return SystemMessage(content=content)
        else:
            # Default fallback
            return SystemMessage(content=f"[Unsupported Message Type: {msg_type}]\n{content}")

class SessionMetadata:
    """Class to store metadata about a session."""
    
    def __init__(self, id: str, name: str = "", created_at: Optional[float] = None, updated_at: Optional[float] = None):
        self.id = id
        self.name = name or f"Session {id[:8]}"  # Default name if none provided
        self.created_at = created_at or time.time()
        self.updated_at = updated_at or self.created_at
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionMetadata':
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time()))
        )

class MemoryManager:
    """A singleton class to manage conversation histories with persistent storage."""
    _instance = None
    _lock = threading.Lock()
    
    # File paths for storage
    STORAGE_DIR = "chat_history"
    METADATA_FILE = os.path.join(STORAGE_DIR, "session_metadata.json")

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):  # Ensure __init__ runs only once
            # Create storage directory if it doesn't exist
            os.makedirs(self.STORAGE_DIR, exist_ok=True)
            
            # Initialize data structures
            self.histories = defaultdict(list)
            self.image_contexts = defaultdict(dict)  # To store image_base64 and report
            self.message_images = defaultdict(dict)  # Maps message_id to image data
            self.session_metadata = {}  # Maps session ID to SessionMetadata
            self.max_history_length = 50
            
            # Load existing data
            self._load_metadata()
            self._load_sessions()
            
            self.initialized = True

    def _get_session_file_path(self, session_id: str) -> str:
        """Get the file path for a session's history."""
        return os.path.join(self.STORAGE_DIR, f"{session_id}.pickle")
    
    def _get_image_file_path(self, session_id: str) -> str:
        """Get the file path for a session's image context."""
        return os.path.join(self.STORAGE_DIR, f"{session_id}_images.pickle")

    def _save_metadata(self):
        """Save session metadata to file."""
        metadata_dict = {id: meta.to_dict() for id, meta in self.session_metadata.items()}
        with open(self.METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata_dict, f, ensure_ascii=False, indent=3)

    def _load_metadata(self):
        """Load session metadata from file."""
        if os.path.exists(self.METADATA_FILE):
            try:
                with open(self.METADATA_FILE, 'r', encoding='utf-8') as f:
                    metadata_dict = json.load(f)
                    
                self.session_metadata = {
                    id: SessionMetadata.from_dict(data) 
                    for id, data in metadata_dict.items()
                }
            except Exception as e:
                print(f"Error loading session metadata: {e}")
                self.session_metadata = {}
    
    def _save_session(self, session_id: str):
        """Save a single session's history and image context to files."""
        if session_id in self.histories:
            # Update the last modified time
            if session_id in self.session_metadata:
                self.session_metadata[session_id].updated_at = time.time()
                self._save_metadata()
            
            # Save history
            history_file = self._get_session_file_path(session_id)
            serialized_history = [
                MessageSerializer.serialize_message(msg) 
                for msg in self.histories[session_id]
            ]
            with open(history_file, 'wb') as f:
                pickle.dump(serialized_history, f)
            
            # Save image context and message images if they exist
            image_data = {
                "image_contexts": self.image_contexts.get(session_id, {}),
                "message_images": self.message_images.get(session_id, {})
            }
            if session_id in self.image_contexts or session_id in self.message_images:
                image_file = self._get_image_file_path(session_id)
                with open(image_file, 'wb') as f:
                    pickle.dump(image_data, f)

    def _load_session(self, session_id: str):
        """Load a single session's history and image context from files."""
        # Load history
        history_file = self._get_session_file_path(session_id)
        if os.path.exists(history_file):
            try:
                with open(history_file, 'rb') as f:
                    serialized_history = pickle.load(f)
                    
                self.histories[session_id] = [
                    MessageSerializer.deserialize_message(msg_data)
                    for msg_data in serialized_history
                ]
            except Exception as e:
                print(f"Error loading session history for {session_id}: {e}")
                self.histories[session_id] = []
        
        # Load image context and message images
        image_file = self._get_image_file_path(session_id)
        if os.path.exists(image_file):
            try:
                with open(image_file, 'rb') as f:
                    image_data = pickle.load(f)
                    # Handle different data structures for backward compatibility
                    if isinstance(image_data, dict) and "image_contexts" in image_data:
                        self.image_contexts[session_id] = image_data.get("image_contexts", {})
                        self.message_images[session_id] = image_data.get("message_images", {})
                    else:
                        # Legacy format - just image context
                        self.image_contexts[session_id] = image_data
                        self.message_images[session_id] = {}
            except Exception as e:
                print(f"Error loading image context for {session_id}: {e}")
                self.image_contexts[session_id] = {}
                self.message_images[session_id] = {}
    
    def _load_sessions(self):
        """Load all sessions from files."""
        for session_id in self.session_metadata.keys():
            self._load_session(session_id)

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
        # Create metadata if this is a new session
        if conversation_id not in self.session_metadata:
            self.session_metadata[conversation_id] = SessionMetadata(id=conversation_id)
        
        # Add messages
        self.histories[conversation_id].extend(messages)
        
        # Trim history to the maximum length
        self.histories[conversation_id] = self.histories[conversation_id][-self.max_history_length:]

        # Save to file
        self._save_session(conversation_id)

    def get_messages_with_images(self, conversation_id: str) -> List[Tuple[HumanMessage, str]]:
        """
        Lấy danh sách các cặp (HumanMessage, image_report) từ lịch sử.
        Mỗi cặp đại diện cho một lần người dùng gửi ảnh và báo cáo tương ứng.
        """
        history = self.histories.get(conversation_id, [])
        image_reports = self.image_contexts.get(conversation_id, {})
        
        # message_id -> image_report
        message_to_report_map = {
            message_id: report 
            for message_id, report in image_reports.items() 
            if "report" in report
        }
        
        # Tìm các HumanMessage có ID tương ứng trong map
        image_messages = []
        for msg in history:
            if isinstance(msg, HumanMessage) and msg.id in message_to_report_map:
                report_data = message_to_report_map[msg.id]
                # Đảm bảo report_data là chuỗi
                report_text = report_data if isinstance(report_data, str) else json.dumps(report_data, ensure_ascii=False)
                image_messages.append((msg, report_text))
                
        return image_messages

    def add_image_to_message(self, conversation_id: str, message_id: str, image_base64: str):
        """Associates an image with a specific message ID."""
        if conversation_id not in self.message_images:
            self.message_images[conversation_id] = {}
        self.message_images[conversation_id][message_id] = image_base64
        self._save_session(conversation_id)

    def add_image_context(self, conversation_id: str, image_base64: str, report: str, message_id: Optional[str] = None):
        """Adds image context (base64 and report) for a conversation."""
        if conversation_id not in self.session_metadata:
            self.session_metadata[conversation_id] = SessionMetadata(id=conversation_id)
            
        self.image_contexts[conversation_id] = {
            "image_base64": image_base64,
            "report": report
        }
        
        # If a message_id is provided, associate the image with that message
        if message_id:
            self.add_image_to_message(conversation_id, message_id, image_base64)
            
        # Immediately save the session to ensure data persistence
        self._save_session(conversation_id)

    def get_image_context(self, conversation_id: str) -> Optional[Dict[str, str]]:
        """DEPRECATED: Retrieves the last image context. Use get_image_for_message instead."""
        # This method is less reliable as it doesn't guarantee the image belongs to the last message.
        context = self.image_contexts.get(conversation_id, {}).get('latest', {})
        return context if context else None

    def get_image_for_message(self, conversation_id: str, message_id: str) -> Optional[str]:
        """
        Retrieves the base64-encoded image associated with a specific message ID.
        """
        image_contexts = self.image_contexts.get(conversation_id, {})
        # The values in image_contexts should be dictionaries, but we add a check for safety
        for context in image_contexts.values():
            if isinstance(context, dict) and context.get('message_id') == message_id:
                return context.get('image_base64')
        return None

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
            
        # Delete the files
        history_file = self._get_session_file_path(conversation_id)
        if os.path.exists(history_file):
            os.remove(history_file)
            
        image_file = self._get_image_file_path(conversation_id)
        if os.path.exists(image_file):
            os.remove(image_file)
            
        # Remove from metadata
        if conversation_id in self.session_metadata:
            del self.session_metadata[conversation_id]
            self._save_metadata()

    def rename_session(self, session_id: str, new_name: str) -> bool:
        """
        Renames a session.
        
        Args:
            session_id: The unique identifier for the conversation.
            new_name: The new name for the session.
            
        Returns:
            True if successful, False if session doesn't exist.
        """
        if session_id not in self.session_metadata:
            return False
            
        self.session_metadata[session_id].name = new_name
        self._save_metadata()
        return True
            
    def list_sessions(self) -> List[Dict[str, Any]]:
        """Returns a list of all sessions with metadata."""
        result = []
        for session_id, metadata in self.session_metadata.items():
            result.append({
                "id": session_id,
                "name": metadata.name,
                "created_at": metadata.created_at,
                "updated_at": metadata.updated_at,
                "message_count": len(self.histories.get(session_id, [])),
                "has_images": session_id in self.image_contexts or any(self.message_images.get(session_id, {}))
            })
        
        # Sort by last updated (most recent first)
        result.sort(key=lambda x: x["updated_at"], reverse=True)
        return result

    def get_history_serializable(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Returns a serializable version of the history for a given session."""
        serializable_history = []
        history = self.get_history(conversation_id)
        
        for msg in history:
            msg_dict = msg.dict()
            message_id = msg_dict.get("id", "")
            
            # First check for message-specific images
            image_base64 = self.get_image_for_message(conversation_id, message_id)
            
            # If no message-specific image and it's a HumanMessage, check for image context
            if not image_base64 and isinstance(msg, HumanMessage):
                image_context = self.get_image_context(conversation_id)
                
                # Check for image_context and report existence before proceeding
                if image_context and "report" in image_context:
                    report = image_context["report"]
                    # Check if this message might be related to the image context
                    if isinstance(msg.content, str) and (
                        "hình ảnh" in msg.content.lower() or 
                        not msg.content.strip() or 
                        "báo giá" in msg.content.lower()
                    ):
                        image_base64 = image_context.get("image_base64", "")
            
            # If we found an image for this message, add it to the content parts
            if image_base64:
                        msg_dict['content_parts'] = [
                    {'type': 'text', 'text': msg_dict.get('content', '')},
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