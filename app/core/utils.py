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


class ProcessLogger:
    """
    Reusable logging utility for specific processes with dedicated log files.
    
    Features:
    - Creates logs directory automatically
    - Clears log file on first use
    - Supports different log levels (INFO, ERROR, DEBUG)
    - Thread-safe writing
    - Context manager support
    
    Usage:
        logger = ProcessLogger("compression_process.log")
        logger.info("Process started")
        logger.error("Something failed", context={"field": "someField", "error": str(e)})
        
        # Or as context manager:
        with ProcessLogger("import_process.log") as logger:
            logger.info("Starting import...")
    """
    
    def __init__(self, filename: str, auto_clear: bool = True):
        """
        Initialize process logger
        
        Args:
            filename: Name of log file (e.g., "compression.log")
            auto_clear: Whether to clear the file on first write (default: True)
        """
        self.filename = filename
        self.auto_clear = auto_clear
        self._first_write = True
        self._setup_log_file()
    
    def _setup_log_file(self):
        """Set up the log file path and create logs directory"""
        # Create logs directory in project root
        self.logs_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # Full path to log file
        self.log_file_path = os.path.join(self.logs_dir, self.filename)
    
    def _write_log(self, level: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Internal method to write log entries"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Clear file on first write if auto_clear is enabled
        if self._first_write and self.auto_clear:
            mode = 'w'
            self._first_write = False
        else:
            mode = 'a'
        
        # Format log entry
        log_entry = f"[{timestamp}] {level}: {message}"
        
        # Add context if provided
        if context:
            context_str = ", ".join([f"{k}={v}" for k, v in context.items()])
            log_entry += f" | Context: {context_str}"
        
        log_entry += "\n"
        
        try:
            with open(self.log_file_path, mode, encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"❌ Failed to write to log file {self.filename}: {e}")
    
    def info(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log an info message"""
        self._write_log("INFO", message, context)
    
    def error(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log an error message"""
        self._write_log("ERROR", message, context)
    
    def debug(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log a debug message"""
        self._write_log("DEBUG", message, context)
    
    def warning(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log a warning message"""
        self._write_log("WARNING", message, context)
    
    def section(self, title: str):
        """Log a section header for better organization"""
        separator = "=" * 50
        self._write_log("SECTION", f"\n{separator}\n{title}\n{separator}")
    
    def success(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log a success message"""
        self._write_log("SUCCESS", f"✅ {message}", context)
    
    def failure(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log a failure message"""
        self._write_log("FAILURE", f"❌ {message}", context)
    
    def get_log_path(self) -> str:
        """Get the full path to the log file"""
        return self.log_file_path
    
    def clear_log(self):
        """Manually clear the log file"""
        try:
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                f.write("")
            self._first_write = True
        except Exception as e:
            print(f"❌ Failed to clear log file {self.filename}: {e}")
    
    # Context manager support
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.error(f"Process terminated with exception: {exc_val}", 
                      context={"exception_type": exc_type.__name__})

 