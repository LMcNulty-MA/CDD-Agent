#!/usr/bin/env python3
"""
Script to populate the CDD database from JSON files.
This script reads the three required JSON files (attributes.json, categories.json, categoryAttributes.json)
and populates the MongoDB database using the FastAPI endpoint.

Usage:
    python scripts/populate_database_from_json.py --attributes attributes.json --categories categories.json --category-attributes categoryAttributes.json
"""

import argparse
import json
import requests
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_json_file(file_path: str) -> list:
    """Load a JSON file and return its contents"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}")
        raise

def populate_database(attributes_file: str, categories_file: str, category_attributes_file: str, api_base_url: str = "http://localhost:5000"):
    """Populate the database using the FastAPI endpoint"""
    
    logger.info("Loading JSON files...")
    
    # Load the JSON files
    attributes_data = load_json_file(attributes_file)
    categories_data = load_json_file(categories_file)
    category_attributes_data = load_json_file(category_attributes_file)
    
    logger.info(f"Loaded {len(attributes_data)} attributes, {len(categories_data)} categories, {len(category_attributes_data)} category-attribute mappings")
    
    # Prepare the request payload
    payload = {
        "attributes_data": attributes_data,
        "categories_data": categories_data,
        "category_attributes_data": category_attributes_data
    }
    
    # Make the API request
    url = f"{api_base_url}/cdd-agent/populate-database"
    
    logger.info(f"Sending request to {url}...")
    
    try:
        response = requests.post(url, json=payload, timeout=300)  # 5 minute timeout
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Database population successful!")
        logger.info(f"Status: {result['status']}")
        logger.info(f"Attributes count: {result['attributes_count']}")
        logger.info(f"Categories count: {result['categories_count']}")
        logger.info(f"Category attributes count: {result['category_attributes_count']}")
        logger.info(f"Message: {result['message']}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error making API request: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Populate CDD database from JSON files")
    parser.add_argument("--attributes", required=True, help="Path to attributes.json file")
    parser.add_argument("--categories", required=True, help="Path to categories.json file") 
    parser.add_argument("--category-attributes", required=True, help="Path to categoryAttributes.json file")
    parser.add_argument("--api-url", default="http://localhost:5000", help="Base URL of the FastAPI application")
    
    args = parser.parse_args()
    
    # Verify files exist
    for file_path in [args.attributes, args.categories, args.category_attributes]:
        if not Path(file_path).exists():
            logger.error(f"File not found: {file_path}")
            return 1
    
    try:
        populate_database(
            args.attributes,
            args.categories, 
            args.category_attributes,
            args.api_url
        )
        logger.info("Database population completed successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"Database population failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main()) 