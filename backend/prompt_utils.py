import os
from pathlib import Path
from typing import Optional, Dict, Any


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"
_prompt_cache = {}

def _load_all_prompts():
    """Load all prompt files into memory at startup"""
    prompts_dir = _prompts_dir()
    for file_path in prompts_dir.glob("*.txt"):
        try:
            _prompt_cache[file_path.name] = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error loading prompt {file_path.name}: {str(e)}")


_load_all_prompts()

def load_prompt(filename: str, variables: Optional[Dict[str, Any]] = None) -> str:
    if filename not in _prompt_cache:
        path = _prompts_dir() / filename
        try:
            _prompt_cache[filename] = path.read_text(encoding="utf-8")
            print(f"Loaded new prompt on-demand: {filename}")
        except Exception:
            print(f"Warning: Prompt file not found: {filename}")
            return ""
    text = _prompt_cache[filename]    
    if variables:
        text_copy = text
        for k, v in variables.items():
            text_copy = text_copy.replace(f"{{{k}}}", str(v))
        return text_copy
    
    return text


def reload_prompts():
    """Reload all prompts from disk, useful during development"""
    _prompt_cache.clear()
    _load_all_prompts()
    return f"Reloaded {len(_prompt_cache)} prompts"


def get_loaded_prompts():
    """Get a list of all loaded prompt filenames"""
    return list(_prompt_cache.keys())
