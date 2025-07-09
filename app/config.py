import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    # Azure OpenAI (replaces OpenAI)
    MODEL_TO_USE: str = "gpt-4.1"

    # MongoDB
    DOCDB_URI: str = ""
    DOCDB_DATABASE_NAME: str = "cdd-agent"

    # Environment
    GLOBAL_ENV: str = ""
    GLOBAL_ENV_CODE: str = ""

    # Logging
    LOG_LEVEL: str = "INFO"

    # SSO Settings
    GLOBAL_SSO_SERVICE_URL: str = ""
    SSO_SERVICE_ID: str = ""
    SSO_SERVICE_SECRET: str = ""

    # Azure Deployment API Related
    GLOBAL_DOCDB_SERVICE_URL: str = ""
    DOCUMENTDB_CONFIG_COLLECTION: str = ""
    AZURE_DEPLOYMENT_API: str = ""
    AZURE_OPENAI_API_KEY: str = ""

    # Prompt debugging
    SAVE_PROMPTS_TO_FILE: bool = True

    # Performance optimization
    MAX_ATTRIBUTES_FOR_MATCHING: int = 50  # Reduce prompt size for better performance

    # Bulk processing settings
    BULK_FIELD_BATCH_SIZE: int = 5  # Number of fields to process in bulk (3-5 recommended)

    # Description compression settings
    MAX_DESCRIPTION_TOKENS: int = 40        # Target compression size
    COMPRESSION_BATCH_SIZE: int = 10        # Process N descriptions at once

    # Output formatting
    DEFAULT_LABEL_TAG: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"  # Allow extra fields in .env file

settings = Settings()