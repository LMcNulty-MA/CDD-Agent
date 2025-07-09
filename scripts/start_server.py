#!/usr/bin/env python3
"""
Startup script for the CDD Mapping Agent API.
This script provides an easy way to start the FastAPI server with proper configuration.

Usage:
    python scripts/start_server.py [--host HOST] [--port PORT] [--reload] [--workers WORKERS]
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import fastapi
        import uvicorn
        import langchain_openai
        import pymongo
        print("✓ All required dependencies are installed")
        return True
    except ImportError as e:
        print(f"✗ Missing dependency: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def check_environment():
    """Check if required environment variables are set"""
    required_vars = ['AZURE_OPENAI_API_KEY', 'DOCDB_URI']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
            
    
    if missing_vars:
        print(f"✗ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file")
        return False
    
    print("✓ Required environment variables are set")
    return True

def check_database_connection():
    """Check if MongoDB connection is working"""
    try:
        # Add project root to Python path
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        
        from app.core.documentdb import MongoDBClient
        from app.config import settings
        
        print(f"Testing connection to MongoDB")
        print(f"Database name: {settings.DOCDB_DATABASE_NAME}")
        
        # Use our existing MongoDBClient class
        client = MongoDBClient(settings.DOCDB_URI, settings.DOCDB_DATABASE_NAME)
        
        # Use the existing test_connection method
        if client.test_connection():
            print(f"✓ Database connection successful to '{settings.DOCDB_DATABASE_NAME}'")
            return True
        else:
            print(f"✗ Database connection test failed")
            return False
            
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("Please check your MongoDB connection string and database name")
        return False

def start_server(host="0.0.0.0", port=5000, reload=False, workers=1):
    """Start the FastAPI server"""
    
    # Change to project root directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    # Build uvicorn command
    cmd = [
        sys.executable, "-m", "uvicorn", 
        "app.main:app",
        "--host", host,
        "--port", str(port)
    ]
    
    if reload:
        cmd.append("--reload")
    elif workers > 1:
        cmd.extend(["--workers", str(workers)])
    
    print(f"Starting CDD Mapping Agent API on http://localhost:{port}")
    print(f"API Documentation: http://localhost:{port}/cdd-agent/docs")
    print("Press Ctrl+C to stop the server")
    print("-" * 60)
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Start the CDD Mapping Agent API server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind the server to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind the server to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code changes")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    parser.add_argument("--skip-checks", action="store_true", help="Skip dependency and environment checks")
    
    args = parser.parse_args()
    
    print("CDD Mapping Agent API Startup")
    print("=" * 40)
    
    if not args.skip_checks:
        # Run pre-flight checks
        if not check_dependencies():
            sys.exit(1)
        
        if not check_environment():
            sys.exit(1)
        
        if not check_database_connection():
            print("⚠ Warning: Database connection failed. The API will start but may not work correctly.")
            response = input("Continue anyway? (y/N): ")
            if response.lower() != 'y':
                sys.exit(1)
    
    # Start the server
    start_server(
        host=args.host,
        port=args.port, 
        reload=args.reload,
        workers=args.workers
    )

if __name__ == "__main__":
    main() 