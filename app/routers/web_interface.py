"""
Web Interface Router

This router provides endpoints for the web-based CDD mapping interface,
focusing on single field checking functionality.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import io
import uuid
import json
import os
import tempfile
from datetime import datetime

from app.core.models import (
    SingleFieldCheckRequest, SingleFieldCheckResponse,
    StandardFieldHeaders, FileProcessingSession, FileUploadResponse,
    ProcessFieldRequest, ProcessFieldResponse, SessionStatusResponse,
    DownloadRequest, CDDMatchResult, NewCDDFieldSuggestion
)
from app.core.services import cdd_mapping_service
from app.core.security import oauth2_scheme
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory session storage (in production, use Redis or database)
processing_sessions: Dict[str, Dict] = {}

# Single Field Check Endpoint
@router.post(
    "/check-field",
    summary="Check Single Field",
    description="Check a single field against CDD attributes and get matches or new field suggestion",
    response_model=SingleFieldCheckResponse,
    status_code=status.HTTP_200_OK
)
async def check_single_field(request: SingleFieldCheckRequest, token: str = Depends(oauth2_scheme)):
    """Check a single field against CDD attributes"""
    try:
        logger.info(f"Checking field: {request.field_name} with action: {request.action_type}")
        
        # Validate token is present (oauth2_scheme should handle this, but double-check)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is required. Please provide a valid Bearer token in the Authorization header.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Use the service to check the field
        result = cdd_mapping_service.check_single_field(
            field_name=request.field_name,
            field_definition=request.field_definition,
            action_type=request.action_type or "find_matches",
            feedback_text=request.feedback_text
        )
        
        logger.info(f"Field check completed with status: {result.status}")
        return result
        
    except HTTPException:
        # Re-raise HTTP exceptions (like auth errors) as-is
        raise
    except Exception as e:
        logger.error(f"Error checking field: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to process field check: {str(e)}. Please verify your input data and try again."
        )

# Get Example File Endpoint
@router.get(
    "/example-file",
    summary="Get Example File",
    description="Download an example file showing the required format",
    status_code=status.HTTP_200_OK
)
async def get_example_file(format: str = "csv", token: str = Depends(oauth2_scheme)):
    """Get an example file showing the required format"""
    try:
        # Validate token is present
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is required. Please provide a valid Bearer token in the Authorization header.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if format not in ["csv", "json"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Format parameter must be either 'csv' or 'json'. Please specify a valid format."
            )
        
        # Create example data
        example_data = [
            {
                "field_name": "LoanAmount",
                "context_definition": "The principal amount of the loan at origination, expressed in the loan currency.",
                "cdd_confirmed": "",
                "cdd_best_guess": ""
            },
            {
                "field_name": "InterestRate",
                "context_definition": "The annual percentage rate (APR) applied to the loan principal.",
                "cdd_confirmed": "",
                "cdd_best_guess": ""
            },
            {
                "field_name": "MaturityDate",
                "context_definition": "The date when the loan reaches full maturity and final payment is due.",
                "cdd_confirmed": "",
                "cdd_best_guess": ""
            }
        ]
        
        if format == "csv":
            # Create CSV content
            df = pd.DataFrame(example_data)
            csv_content = df.to_csv(index=False)
            
            return StreamingResponse(
                io.StringIO(csv_content),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=example_cdd_mapping.csv"}
            )
        else:
            # Create JSON content
            import json
            json_content = json.dumps(example_data, indent=2)
            
            return StreamingResponse(
                io.StringIO(json_content),
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=example_cdd_mapping.json"}
            )
        
    except HTTPException:
        # Re-raise HTTP exceptions (like auth errors) as-is
        raise
    except Exception as e:
        logger.error(f"Error creating example file: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to generate example file: {str(e)}. Please try again or contact support."
        )

# File Upload Endpoint
@router.post(
    "/upload-file",
    summary="Upload File for Processing",
    description="Upload a CSV or JSON file for batch field processing",
    response_model=FileUploadResponse,
    status_code=status.HTTP_200_OK
)
async def upload_file(
    file: UploadFile = File(...),
    token: str = Depends(oauth2_scheme)
):
    """Upload and process a file for CDD mapping"""
    try:
        # Validate token
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is required.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Validate file type
        if not file.filename or not file.filename.lower().endswith(('.csv', '.json')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only CSV and JSON files are supported."
            )
        
        # Read file content
        content = await file.read()
        
        # Parse file based on extension
        if file.filename and file.filename.lower().endswith('.json'):
            try:
                data = json.loads(content.decode('utf-8'))
                df = pd.DataFrame(data)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON format. Please check your file."
                )
        else:
            # CSV file
            try:
                df = pd.read_csv(io.StringIO(content.decode('utf-8')))
            except UnicodeDecodeError:
                # Try different encodings
                for encoding in ['windows-1252', 'latin-1']:
                    try:
                        df = pd.read_csv(io.StringIO(content.decode(encoding)))
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Unable to read CSV file. Please check the file encoding."
                    )
        
        # Standardize column names (same logic as cdd_mapping.py)
        column_mapping = {}
        for col in df.columns:
            col_lower = col.lower().strip()
            if any(term in col_lower for term in ['field', 'name']) and 'context' not in col_lower and 'cdd' not in col_lower:
                column_mapping[col] = StandardFieldHeaders.FIELD_NAME.value
            elif any(term in col_lower for term in ['context', 'definition', 'description', 'notes']) and 'cdd' not in col_lower:
                column_mapping[col] = StandardFieldHeaders.CONTEXT_DEFINITION.value
            elif 'cdd_confirmed' in col_lower or 'confirmed' in col_lower:
                column_mapping[col] = StandardFieldHeaders.CDD_CONFIRMED.value
            elif 'cdd_best_guess' in col_lower or 'best_guess' in col_lower or ('cdd' in col_lower and any(term in col_lower for term in ['field', 'name', 'guess'])):
                column_mapping[col] = StandardFieldHeaders.CDD_BEST_GUESS.value
        
        # Rename columns to standard format
        df = df.rename(columns=column_mapping)
        
        # Validate required columns
        required_cols = [StandardFieldHeaders.FIELD_NAME.value, StandardFieldHeaders.CONTEXT_DEFINITION.value]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required columns: {missing_cols}. Expected: field_name, context_definition"
            )
        
        # Add missing columns if not present
        if StandardFieldHeaders.CDD_CONFIRMED.value not in df.columns:
            df[StandardFieldHeaders.CDD_CONFIRMED.value] = ""
        if StandardFieldHeaders.CDD_BEST_GUESS.value not in df.columns:
            df[StandardFieldHeaders.CDD_BEST_GUESS.value] = ""
        
        # Convert to object dtype to avoid pandas warnings
        df[StandardFieldHeaders.CDD_CONFIRMED.value] = df[StandardFieldHeaders.CDD_CONFIRMED.value].astype('object')
        df[StandardFieldHeaders.CDD_BEST_GUESS.value] = df[StandardFieldHeaders.CDD_BEST_GUESS.value].astype('object')
        
        # Filter processable fields (same logic as cdd_mapping.py)
        field_col = StandardFieldHeaders.FIELD_NAME.value
        context_col = StandardFieldHeaders.CONTEXT_DEFINITION.value
        confirmed_col = StandardFieldHeaders.CDD_CONFIRMED.value
        best_guess_col = StandardFieldHeaders.CDD_BEST_GUESS.value
        
        skip_mask = (
            (df[confirmed_col].notna() & (df[confirmed_col].astype(str).str.strip() != "")) |
            (df[best_guess_col].notna() & (df[best_guess_col].astype(str).str.strip() != "")) |
            (df[context_col].astype(str).str.contains("NEED REVIEW", case=False, na=False)) |
            (df[field_col].isna() | (df[field_col].astype(str).str.strip() == "")) |
            (df[context_col].isna() | (df[context_col].astype(str).str.strip() == ""))
        )
        
        processable_df = df.loc[~skip_mask].copy()
        
        # Create session
        session_id = str(uuid.uuid4())
        
        # Store session data
        processing_sessions[session_id] = {
            'session_id': session_id,
            'original_filename': file.filename,
            'original_df': df.to_dict('records'),
            'processable_indices': processable_df.index.tolist(),
            'current_index': 0,
            'total_fields': len(df),
            'processable_fields': len(processable_df),
            'processed_fields': 0,
            'status': 'active',
            'created_at': datetime.now(),
            'last_updated': datetime.now(),
            'new_field_suggestions': []
        }
        
        return FileUploadResponse(
            session_id=session_id,
            message=f"File uploaded successfully. {len(processable_df)} fields ready for processing.",
            total_fields=len(df),
            processable_fields=len(processable_df),
            sample_fields=[]  # Removed confusing sample fields
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to process uploaded file: {str(e)}"
        )

# Get Next Field Endpoint
@router.get(
    "/session/{session_id}/next-field",
    summary="Get Next Field to Process",
    description="Get the next field in the session for processing",
    status_code=status.HTTP_200_OK
)
async def get_next_field(session_id: str, token: str = Depends(oauth2_scheme)):
    """Get the next field to process in the session"""
    try:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is required.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if session_id not in processing_sessions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = processing_sessions[session_id]
        
        if session['current_index'] >= len(session['processable_indices']):
            return {
                'session_id': session_id,
                'status': 'completed',
                'progress': {
                    'total': session['processable_fields'],
                    'processed': session['processed_fields'],
                    'remaining': 0
                },
                'current_field': None,
                'can_download': True
            }
        
        # Get current field
        current_df_index = session['processable_indices'][session['current_index']]
        current_row = session['original_df'][current_df_index]
        
        # Get matches for the current field automatically (per user workflow)
        field_name = current_row[StandardFieldHeaders.FIELD_NAME.value]
        field_definition = current_row[StandardFieldHeaders.CONTEXT_DEFINITION.value]
        
        # Use the service to get matches automatically
        check_result = cdd_mapping_service.check_single_field(
            field_name=field_name, 
            field_definition=field_definition,
            action_type="find_matches"
        )
        
        return {
            'session_id': session_id,
            'status': 'active',
            'progress': {
                'total': session['processable_fields'],
                'processed': session['processed_fields'],
                'remaining': session['processable_fields'] - session['processed_fields']
            },
            'current_field': {
                'index': session['current_index'],
                'field_name': field_name,
                'field_definition': field_definition,
                'matches': [match.dict() for match in check_result.matches],
                'new_field_suggestion': check_result.new_field_suggestion.dict() if check_result.new_field_suggestion else None,
                'status': check_result.status
            },
            'can_download': session['processed_fields'] > 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting next field: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to get next field: {str(e)}"
        )

# Process Field Action Endpoint
@router.post(
    "/session/{session_id}/process-field",
    summary="Process Field Action",
    description="Process a field with the selected action (match, new_field, skip)",
    status_code=status.HTTP_200_OK
)
async def process_field_action(
    session_id: str,
    action: str = Form(...),
    selected_match: Optional[str] = Form(None),
    new_field_json: Optional[str] = Form(None),
    feedback_history: Optional[str] = Form(None),
    token: str = Depends(oauth2_scheme)
):
    """Process a field action in the session"""
    try:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is required.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if session_id not in processing_sessions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = processing_sessions[session_id]
        
        if session['current_index'] >= len(session['processable_indices']):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No more fields to process"
            )
        
        # Get current field
        current_df_index = session['processable_indices'][session['current_index']]
        current_row = session['original_df'][current_df_index]
        field_name = current_row[StandardFieldHeaders.FIELD_NAME.value]
        
        # Process the action
        updated_value = None
        
        if action == 'match' and selected_match:
            # Update with selected match
            updated_value = selected_match
            session['original_df'][current_df_index][StandardFieldHeaders.CDD_BEST_GUESS.value] = selected_match
            
        elif action == 'new_field':
            # Handle new field creation
            if new_field_json:
                try:
                    new_field_data = json.loads(new_field_json)
                    # Store the new field suggestion
                    session['new_field_suggestions'].append(new_field_data)
                    updated_value = "NEW_FIELD_REQUESTED"
                    session['original_df'][current_df_index][StandardFieldHeaders.CDD_BEST_GUESS.value] = "NEW_FIELD_REQUESTED"
                except json.JSONDecodeError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid new field data format"
                    )
            else:
                # Generate new field suggestion
                field_definition = current_row[StandardFieldHeaders.CONTEXT_DEFINITION.value]
                feedback_list = json.loads(feedback_history) if feedback_history else None
                
                check_result = cdd_mapping_service.check_single_field(
                    field_name=field_name, 
                    field_definition=field_definition, 
                    action_type="create_new_field",
                    feedback_text=feedback_history
                )
                
                if check_result.new_field_suggestion:
                    session['new_field_suggestions'].append(check_result.new_field_suggestion.dict())
                    updated_value = "NEW_FIELD_REQUESTED"
                    session['original_df'][current_df_index][StandardFieldHeaders.CDD_BEST_GUESS.value] = "NEW_FIELD_REQUESTED"
                else:
                    updated_value = "SKIP"
                    session['original_df'][current_df_index][StandardFieldHeaders.CDD_BEST_GUESS.value] = "SKIP"
                    
        elif action == 'skip':
            # Skip the field
            updated_value = "SKIP"
            session['original_df'][current_df_index][StandardFieldHeaders.CDD_BEST_GUESS.value] = "SKIP"
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid action or missing required parameters"
            )
        
        # Update session progress
        session['processed_fields'] += 1
        session['current_index'] += 1
        session['last_updated'] = datetime.now()
        
        # Check if completed
        if session['current_index'] >= len(session['processable_indices']):
            session['status'] = 'completed'
        
        return {
            'session_id': session_id,
            'field_index': session['current_index'] - 1,
            'field_name': field_name,
            'action_taken': action,
            'updated_value': updated_value,
            'progress': {
                'total': session['processable_fields'],
                'processed': session['processed_fields'],
                'remaining': session['processable_fields'] - session['processed_fields']
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing field action: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to process field action: {str(e)}"
        )

# Download Files Endpoint
@router.get(
    "/session/{session_id}/download",
    summary="Download Processed Files",
    description="Download the updated input file and new field suggestions",
    status_code=status.HTTP_200_OK
)
async def download_files(
    session_id: str,
    file_type: str,
    format: str = "csv",
    token: str = Depends(oauth2_scheme)
):
    """Download processed files from the session"""
    try:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is required.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if session_id not in processing_sessions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = processing_sessions[session_id]
        
        if file_type == "updated_input":
            # Return updated input file
            df = pd.DataFrame(session['original_df'])
            
            if format == "json":
                content = df.to_json(orient='records', indent=2)
                media_type = "application/json"
                filename = f"updated_{session['original_filename'].rsplit('.', 1)[0]}.json"
            else:
                content = df.to_csv(index=False)
                media_type = "text/csv"
                filename = f"updated_{session['original_filename'].rsplit('.', 1)[0]}.csv"
                
        elif file_type == "new_fields":
            # Return new field suggestions
            if not session['new_field_suggestions']:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No new field suggestions available"
                )
            
            # Format new field suggestions with proper column names
            formatted_suggestions = []
            for suggestion in session['new_field_suggestions']:
                formatted_suggestion = {
                    "Category": suggestion.get('category', ''),
                    "Attribute": suggestion.get('attribute', ''),
                    "Description": suggestion.get('description', ''),
                    "Label": suggestion.get('label', ''),
                    "Tag": suggestion.get('tag', settings.DEFAULT_LABEL_TAG),
                    "New - Update - Deprecate (NOTE: ALWAYS NEW FOR NOW)": "New",
                    "Partition Key Order (NOTE: LEAVE EMPTY FOR NOW)": "",
                    "Index Key (NOTE: LEAVE EMPTY FOR NOW)": ""
                }
                formatted_suggestions.append(formatted_suggestion)
            
            df = pd.DataFrame(formatted_suggestions)
            
            if format == "json":
                content = df.to_json(orient='records', indent=2)
                media_type = "application/json"
                filename = f"new_field_suggestions_{session_id[:8]}.json"
            else:
                content = df.to_csv(index=False)
                media_type = "text/csv"
                filename = f"new_field_suggestions_{session_id[:8]}.csv"
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file_type. Must be 'updated_input' or 'new_fields'"
            )
        
        return StreamingResponse(
            io.StringIO(content),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading files: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to download files: {str(e)}"
        )

# Download Single Field New Field Suggestion Endpoint
@router.post(
    "/download-single-field-suggestion",
    summary="Download Single Field New Field Suggestion",
    description="Download a new field suggestion for a single field in CSV or JSON format",
    status_code=status.HTTP_200_OK
)
async def download_single_field_suggestion(
    field_name: str = Form(...),
    field_definition: str = Form(...),
    new_field_json: str = Form(...),
    format: str = Form("csv"),
    token: str = Depends(oauth2_scheme)
):
    """Download a single field's new field suggestion"""
    try:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is required.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Parse the new field data
        try:
            new_field_data = json.loads(new_field_json)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid new field data format"
            )
        
        # Format the new field suggestion with proper column names for template
        formatted_suggestion = {
            "Category": new_field_data.get('category', ''),
            "Attribute": new_field_data.get('attribute', ''),
            "Description": new_field_data.get('description', ''),
            "Label": new_field_data.get('label', ''),
            "Tag": new_field_data.get('tag', settings.DEFAULT_LABEL_TAG),
            "New - Update - Deprecate (NOTE: ALWAYS NEW FOR NOW)": "New",
            "Partition Key Order (NOTE: LEAVE EMPTY FOR NOW)": "",
            "Index Key (NOTE: LEAVE EMPTY FOR NOW)": "",
            "Data Type": new_field_data.get('data_type', 'STRING'),
            "Original Field Name": field_name,
            "Original Field Definition": field_definition,
            "Created At": datetime.now().isoformat()
        }
        
        # Create file content
        if format == "json":
            content = json.dumps([formatted_suggestion], indent=2)
            media_type = "application/json"
            filename = f"new_field_suggestion_{field_name.replace(' ', '_')}.json"
        else:
            df = pd.DataFrame([formatted_suggestion])
            content = df.to_csv(index=False)
            media_type = "text/csv"
            filename = f"new_field_suggestion_{field_name.replace(' ', '_')}.csv"
        
        return StreamingResponse(
            io.StringIO(content),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading single field suggestion: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to download field suggestion: {str(e)}"
        )

# Static file serving routes
@router.get("/static/css/{file_path:path}")
async def serve_css(file_path: str):
    """Serve CSS files"""
    return FileResponse(f"app/static/css/{file_path}")

@router.get("/static/js/{file_path:path}")
async def serve_js(file_path: str):
    """Serve JavaScript files"""
    return FileResponse(f"app/static/js/{file_path}")

@router.get("/static/html/{file_path:path}")
async def serve_html(file_path: str):
    """Serve HTML files"""
    return FileResponse(f"app/static/html/{file_path}")

# Web Interface HTML Page
@router.get(
    "/",
    summary="CDD Mapping Web Interface",
    description="Serve the main web interface HTML page",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK
)
async def web_interface():
    """Serve the main web interface"""
    return FileResponse("app/static/html/main.html") 