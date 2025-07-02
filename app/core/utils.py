import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

# Import settings to check if prompt saving is enabled
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.config import settings

def ensure_prompts_directory():
    """Ensure the prompts_out directory exists"""
    prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts_out")
    if not os.path.exists(prompts_dir):
        os.makedirs(prompts_dir)
    return prompts_dir

def save_matching_prompt(field_name: str, field_definition: str, prompt: str, response: Optional[str] = None):
    """Save field matching prompt to file (full prompt and response, no truncation)"""
    if not settings.SAVE_PROMPTS_TO_FILE:
        return
    
    prompts_dir = ensure_prompts_directory()
    clean_field_name = "".join(c for c in field_name if c.isalnum() or c in ('-', '_'))[:50]
    filename = f"matching_{clean_field_name}.txt"
    filepath = os.path.join(prompts_dir, filename)
    content = f"""FIELD MATCHING PROMPT\n=====================\nTimestamp: {datetime.now().isoformat()}\nField Name: {field_name}\nField Definition: {field_definition}\n\nFULL PROMPT SENT:\n=================\n{prompt}\n\nRESPONSE RECEIVED:\n==================\n{response if response else 'Not captured'}\n"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"📝 Matching prompt saved to: {filename}")
    except Exception as e:
        print(f"❌ Error saving matching prompt: {e}")

def save_new_field_prompt(field_name: str, field_definition: str, prompt: str, response: Optional[str] = None, iteration: int = 1, feedback: str = ""):
    """Save new field creation prompt to file (full prompt and response, no truncation)"""
    if not settings.SAVE_PROMPTS_TO_FILE:
        return
    
    prompts_dir = ensure_prompts_directory()
    clean_field_name = "".join(c for c in field_name if c.isalnum() or c in ('-', '_'))[:50]
    filename = f"newfield_{clean_field_name}_iter{iteration}.txt"
    filepath = os.path.join(prompts_dir, filename)
    content = f"""NEW FIELD CREATION PROMPT\n=========================\nTimestamp: {datetime.now().isoformat()}\nField Name: {field_name}\nField Definition: {field_definition}\nIteration: {iteration}\nFeedback: {feedback if feedback else 'None'}\n\nFULL PROMPT SENT:\n=================\n{prompt}\n\nRESPONSE RECEIVED:\n==================\n{response if response else 'Not captured'}\n"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"📝 New field prompt saved to: {filename}")
    except Exception as e:
        print(f"❌ Error saving new field prompt: {e}")

def save_prompt_summary(session_summary: Dict[str, Any]):
    """Save a summary of all prompts from a session"""
    if not settings.SAVE_PROMPTS_TO_FILE:
        return
        
    prompts_dir = ensure_prompts_directory()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"session_summary_{timestamp}.json"
    filepath = os.path.join(prompts_dir, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(session_summary, f, indent=2, default=str)
        print(f"📝 Session summary saved to: {filename}")
    except Exception as e:
        print(f"❌ Error saving session summary: {e}")

def save_prompt_and_response(prompt: str, output_file: str, response: Optional[str] = None):
    """Save the exact prompt and response to the specified file, overwriting it."""
    if not settings.SAVE_PROMPTS_TO_FILE:
        return
    content = f"PROMPT SENT:\n\n{prompt}\n\nRESPONSE RECEIVED:\n\n{response if response else 'Not captured'}\n"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)

 