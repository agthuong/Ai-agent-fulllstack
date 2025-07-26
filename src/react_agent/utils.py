"""Utility & helper functions."""

from langchain_ollama import ChatOllama
import re


def cleanup_llm_output(text: str) -> str:
    """
    Cleans up the raw output from the LLM.

    This function performs two main tasks:
    1. Removes any <think>...</think> blocks used by the model for reasoning.
    2. Strips any markdown formatting (like ```json ... ```) that the model
       might wrap around a JSON output.

    Args:
        text: The raw string output from the LLM.

    Returns:
        A cleaned string ready for parsing or further processing.
    """
    if not isinstance(text, str):
        return ""

    # 1. Remove <think>...</think> blocks
    # The re.DOTALL flag allows '.' to match newlines, handling multi-line think blocks.
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # 2. Strip JSON markdown formatting
    # This regex looks for optional "json" language identifier and strips the backticks.
    match = re.search(r'```(json)?\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        text = match.group(2).strip()

    return text


def load_chat_model(model_name: str):
    """
    Loads an Ollama chat model.

    Args:
        model_name: The name of the Ollama model to load (e.g., "qwen2:7b").

    Returns:
        An instance of ChatOllama.
    """
    # This is a simple wrapper for loading Ollama models.
    # This can be extended later to include other configurations like base_url.
    return ChatOllama(model=model_name)

def _format_history(messages: list) -> str:
    """Helper to format the history for the prompt."""
    if not messages:
        return "No history."
    # A simple formatting for now, can be improved later.
    return "\\n".join([f"{msg.type}: {msg.content}" for msg in messages])

def _parse_area_map_from_message(content: str) -> dict:
    """Parses a pre-processed message to extract a detailed area_map."""
    area_map = {}
    # Regex patterns now account for optional dimension descriptions like (dài 8m)
    patterns = {
        "sàn": r"- Diện tích sàn: ([\\d.]+)m²",
        "trần": r"- Diện tích trần: ([\\d.]+)m²",
        "tường 1": r"- Diện tích tường 1(?: \\(.*\\))?: ([\\d.]+)m²",
        "tường 2": r"- Diện tích tường 2(?: \\(.*\\))?: ([\\d.]+)m²",
        "tường 3": r"- Diện tích tường 3(?: \\(.*\\))?: ([\\d.]+)m²",
        "tường 4": r"- Diện tích tường 4(?: \\(.*\\))?: ([\\d.]+)m²",
    }
    
    for surface, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            area_map[surface] = {"area": f"{match.group(1)}m²"}

    return area_map
