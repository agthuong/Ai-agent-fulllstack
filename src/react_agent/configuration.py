"""Define the configurable parameters for the agent."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Annotated, Optional, List, Dict, Any, Union

from langchain_core.runnables import ensure_config
from langgraph.config import get_config
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, BaseMessage
from langgraph.checkpoint.base import BaseCheckpointSaver

from react_agent import prompts


@dataclass
class Configuration:
    """Defines the configurable parameters for the agent."""

    model: str = "qwen3:30b"
    """The main, powerful model for complex tasks like planning and responding."""
    
    fast_model: str = "qwen3:30b"
    """A faster, smaller model for simpler tasks like tool selection."""

    checkpoint_saver: Optional[BaseCheckpointSaver] = field(default=None)
    """An optional checkpoint saver for persisting agent state."""

    # The system_prompt will be injected at runtime from the config
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    _context: Optional[Any] = field(default=None, repr=False)

    @classmethod
    def from_context(cls) -> Configuration:
        """Create a Configuration instance from a RunnableConfig object."""
        try:
            config = get_config()
        except RuntimeError:
            config = None
        config = ensure_config(config)
        configurable = config.get("configurable") or {}
        _fields = {f.name for f in fields(cls) if f.init}
        return cls(**{k: v for k, v in configurable.items() if k in _fields})
