import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str = ""
    MODEL_TO_USE: str = "gpt-4.1"
    
    # MongoDB
    DOCDB_URI: str = ""
    DOCDB_DATABASE_NAME: str = "cdd-agent"
    
    # SSO Settings
    GLOBAL_SSO_SERVICE_URL: str = ""
    
    # File paths for CDD mapping
    FIELD_NEED_MAPPING_FILE: str = r"C:\Users\McNultyL\OneDrive - moodys.com\Documents\GitHub\ai-field-mapping\ZM Engine Fields.csv"
    NEW_CDD_FIELD_REQUEST_FILE: str = r"C:\Users\McNultyL\OneDrive - moodys.com\Documents\GitHub\ai-field-mapping\ZM_New_CDD_Field_Requests.csv"
    
    # Prompt debugging
    SAVE_PROMPTS_TO_FILE: bool = False
    
    # Output formatting
    DEFAULT_LABEL_TAG: str = "ZM/OALM"
    
    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"  # Allow extra fields in .env file

settings = Settings()