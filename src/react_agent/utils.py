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
    # It can be extended later to include other configurations like base_url.
    return ChatOllama(model=model_name)
