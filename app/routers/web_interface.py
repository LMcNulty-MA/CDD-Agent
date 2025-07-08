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
    DownloadRequest, CDDMatchResult, NewCDDFieldSuggestion,
    BulkFieldData, BulkFieldCheckRequest, BulkFieldCheckResponse, BulkFieldResult
)
from app.core.services import cdd_mapping_service
from app.core.auth_utils import token_dependency
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
async def check_single_field(request: SingleFieldCheckRequest, token: str = Depends(token_dependency)):
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
    summary="Get Example Excel File",
    description="Download an example Excel file with both tabs showing the required format",
    status_code=status.HTTP_200_OK
)
async def get_example_file(token: str = Depends(token_dependency)):
    """Get an example Excel file with both tabs showing the required format"""
    try:
        # Validate token is present
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is required. Please provide a valid Bearer token in the Authorization header.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Create example data for fields_to_map tab
        fields_to_map_data = [
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
        
        # Create example data for new_suggested_fields tab
        new_suggested_fields_data = [
            {
                "Category": "Loan Details",
                "Attribute": "example_new_field",
                "Description": "This is an example of a new field suggestion that would be populated during processing",
                "Label": "Example New Field"
            }
        ]
        
        # Create Excel file with both tabs - Fixed Windows file locking issue
        temp_file = None
        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
            temp_file.close()  # Close file handle to allow Excel writer to use it
            
            # Create Excel content
            with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
                # Create fields_to_map tab
                fields_df = pd.DataFrame(fields_to_map_data)
                fields_df.to_excel(writer, sheet_name='fields_to_map', index=False)
                
                # Create new_suggested_fields tab
                suggestions_df = pd.DataFrame(new_suggested_fields_data)
                suggestions_df.to_excel(writer, sheet_name='new_suggested_fields', index=False)
            
            # Read the file content
            with open(temp_file.name, 'rb') as f:
                excel_content = f.read()
            
        finally:
            # Clean up temp file
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except (OSError, PermissionError) as e:
                    logger.warning(f"Could not delete temporary file {temp_file.name}: {e}")
        
        return StreamingResponse(
            io.BytesIO(excel_content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=\"example_cdd_mapping.xlsx\"",
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
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
    description="Upload an Excel file for batch field processing",
    response_model=FileUploadResponse,
    status_code=status.HTTP_200_OK
)
async def upload_file(
    file: UploadFile = File(...),
    token: str = Depends(token_dependency)
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
        if not file.filename or not file.filename.lower().endswith('.xlsx'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only Excel (.xlsx) files are supported."
            )
        
        # Read Excel file content
        content = await file.read()
        
        # Parse Excel file - read from "fields_to_map" tab
        try:
            with io.BytesIO(content) as excel_buffer:
                # Try to read the "fields_to_map" sheet
                try:
                    df = pd.read_excel(excel_buffer, sheet_name='fields_to_map')
                except ValueError:
                    # If "fields_to_map" sheet doesn't exist, try the first sheet
                    try:
                        df = pd.read_excel(excel_buffer, sheet_name=0)
                    except Exception:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Unable to read Excel file. Please ensure it has a 'fields_to_map' sheet or valid data in the first sheet."
                        )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to read Excel file: {str(e)}. Please check the file format."
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
        
        # Store session data with original filename
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
            'new_field_suggestions': [],
            'bulk_results_cache': {},  # Cache for bulk processing results
            'current_bulk_batch': None,  # Current batch being processed
            'bulk_batch_size': settings.BULK_FIELD_BATCH_SIZE  # Configurable batch size
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

# Bulk Field Processing Endpoint
@router.post(
    "/session/{session_id}/bulk-process",
    summary="Process Multiple Fields in Bulk",
    description="Process multiple fields at once for better performance",
    response_model=BulkFieldCheckResponse,
    status_code=status.HTTP_200_OK
)
async def bulk_process_fields(
    session_id: str,
    feedback_text: Optional[str] = Form(None),
    token: str = Depends(token_dependency)
):
    """Process multiple fields in bulk for better performance"""
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
        batch_size = session['bulk_batch_size']
        
        # Get the next batch of fields to process
        start_index = session['current_index']
        end_index = min(start_index + batch_size, len(session['processable_indices']))
        
        logger.info(f"Processing batch: {end_index - start_index} fields (batch size: {batch_size})")
        
        if start_index >= len(session['processable_indices']):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No more fields to process"
            )
        
        # Prepare fields for bulk processing
        fields_to_process = []
        for i in range(start_index, end_index):
            df_index = session['processable_indices'][i]
            field_row = session['original_df'][df_index]
            fields_to_process.append({
                'field_name': field_row[StandardFieldHeaders.FIELD_NAME.value],
                'field_definition': field_row[StandardFieldHeaders.CONTEXT_DEFINITION.value]
            })
        
        # Process fields in bulk using the service
        import time
        start_time = time.time()
        
        bulk_results = cdd_mapping_service.check_bulk_fields(
            fields=fields_to_process,
            feedback_text=feedback_text
        )
        
        processing_time = time.time() - start_time
        
        # Convert results to response format and cache them
        response_results = []
        for i, field_data in enumerate(fields_to_process):
            field_name = field_data['field_name']
            matches = bulk_results.get(field_name, [])
            df_index = session['processable_indices'][start_index + i]
            processable_index = start_index + i  # The position in the processable_indices array
            
            # Convert matches to CDDMatchResult format
            match_results = []
            for match in matches:
                match_result = CDDMatchResult(
                    cdd_field=match['name'],
                    display_name=match.get('display_name'),
                    data_type=match.get('data_type'),
                    description=match.get('description'),
                    category=match.get('category'),
                    confidence_score=match['confidence_score']
                )
                match_results.append(match_result)
            
            # Determine status
            field_status = "no_match"
            if match_results and match_results[0].confidence_score >= 0.6:
                field_status = "matched"
            
            bulk_field_result = BulkFieldResult(
                field_name=field_name,
                field_definition=field_data['field_definition'],
                index=df_index,
                processable_index=processable_index,
                matches=match_results,
                new_field_suggestion=None,
                status=field_status,
                confidence_threshold=0.6
            )
            response_results.append(bulk_field_result)
            
            # Cache the results for individual field processing
            session['bulk_results_cache'][field_name] = {
                'matches': match_results,
                'status': field_status,
                'processed_at': datetime.now()
            }
        
        # Update session state
        session['current_bulk_batch'] = {
            'fields': fields_to_process,
            'results': response_results,
            'start_index': start_index,
            'end_index': end_index
        }
        session['last_updated'] = datetime.now()
        
        logger.info(f"Bulk processing completed: {len(response_results)} fields in {processing_time:.2f}s")
        
        return BulkFieldCheckResponse(
            session_id=session_id,
            results=response_results,
            total_processed=len(response_results),
            feedback_applied=bool(feedback_text),
            processing_time=processing_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk field processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to process fields in bulk: {str(e)}"
        )

# Get Next Field Endpoint
@router.get(
    "/session/{session_id}/next-field",
    summary="Get Next Field to Process",
    description="Get the next field in the session for processing",
    status_code=status.HTTP_200_OK
)
async def get_next_field(session_id: str, token: str = Depends(token_dependency)):
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
        
        # Check if all fields are processed
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
                'can_download': True,
                'batch_info': {
                    'batch_size': session['bulk_batch_size'],
                    'need_bulk_processing': False,
                    'current_batch_start': None,
                    'current_batch_end': None
                }
            }
        
        # Get current field
        current_df_index = session['processable_indices'][session['current_index']]
        current_row = session['original_df'][current_df_index]
        
        field_name = current_row[StandardFieldHeaders.FIELD_NAME.value]
        field_definition = current_row[StandardFieldHeaders.CONTEXT_DEFINITION.value]
        
        # Check if we need to process the next batch
        batch_size = session['bulk_batch_size']
        current_batch_start = (session['current_index'] // batch_size) * batch_size
        current_batch_end = min(current_batch_start + batch_size, len(session['processable_indices']))
        
        # Check if we have cached bulk results for this field
        need_bulk_processing = False
        if field_name not in session['bulk_results_cache']:
            need_bulk_processing = True
            logger.info(f"Field {field_name} not in cache, bulk processing needed for batch starting at {current_batch_start}")
        
        if field_name in session['bulk_results_cache']:
            cached_result = session['bulk_results_cache'][field_name]
            matches = cached_result['matches']
            field_status = cached_result['status']
            
            # Convert cached matches to dict format for response
            matches_dict = [match.dict() for match in matches]
        else:
            # No cached results - bulk processing needed
            matches_dict = []
            field_status = 'pending'
        
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
                'matches': matches_dict,
                'new_field_suggestion': None,
                'status': field_status,
                'processed': field_name in session['bulk_results_cache']
            },
            'can_download': session['processed_fields'] > 0,
            'batch_info': {
                'batch_size': batch_size,
                'need_bulk_processing': need_bulk_processing,
                'current_batch_start': current_batch_start,
                'current_batch_end': current_batch_end,
                'fields_in_current_batch': current_batch_end - current_batch_start,
                'batch_progress': session['current_index'] - current_batch_start + 1 if not need_bulk_processing else 0
            }
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
    token: str = Depends(token_dependency)
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
    summary="Download Updated Mapping File",
    description="Download the complete Excel file with updated mappings and new field suggestions",
    status_code=status.HTTP_200_OK
)
async def download_files(
    session_id: str,
    token: str = Depends(token_dependency)
):
    """Download the complete Excel file with updated mappings and new field suggestions"""
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
        
        # Create updated fields_to_map data
        fields_to_map_df = pd.DataFrame(session['original_df'])
        
        # Create new_suggested_fields data
        new_suggested_fields_data = []
        for suggestion in session['new_field_suggestions']:
            formatted_suggestion = {
                "Category": suggestion.get('category', ''),
                "Attribute": suggestion.get('attribute', ''),
                "Description": suggestion.get('description', ''),
                "Label": suggestion.get('label', '')
            }
            new_suggested_fields_data.append(formatted_suggestion)
        
        # Create Excel file with both tabs - Fixed Windows file locking issue
        temp_file = None
        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
            temp_file.close()  # Close file handle to allow Excel writer to use it
            
            # Create Excel content
            with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
                # Write fields_to_map tab (updated with processed data)
                fields_to_map_df.to_excel(writer, sheet_name='fields_to_map', index=False)
                
                # Write new_suggested_fields tab (only if there are suggestions)
                if new_suggested_fields_data:
                    new_suggested_fields_df = pd.DataFrame(new_suggested_fields_data)
                    new_suggested_fields_df.to_excel(writer, sheet_name='new_suggested_fields', index=False)
                else:
                    # Create empty sheet with headers
                    empty_suggestions_df = pd.DataFrame({
                        "Category": [],
                        "Attribute": [],
                        "Description": [],
                        "Label": []
                    })
                    empty_suggestions_df.to_excel(writer, sheet_name='new_suggested_fields', index=False)
            
            # Read the file content
            with open(temp_file.name, 'rb') as f:
                excel_content = f.read()
            
        finally:
            # Clean up temp file
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except (OSError, PermissionError) as e:
                    logger.warning(f"Could not delete temporary file {temp_file.name}: {e}")
        
        # Generate filename with timestamp
        original_name = session['original_filename'].rsplit('.', 1)[0] if session['original_filename'] else "processed_mapping"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{original_name}_{timestamp}.xlsx"
        
        return StreamingResponse(
            io.BytesIO(excel_content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
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
    description="Download a new field suggestion for a single field in Excel format",
    status_code=status.HTTP_200_OK
)
async def download_single_field_suggestion(
    field_name: str = Form(...),
    field_definition: str = Form(...),
    new_field_json: str = Form(...),
    token: str = Depends(token_dependency)
):
    """Download a single field's new field suggestion as Excel file"""
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
        
        # Format the new field suggestion
        formatted_suggestion = {
            "Category": new_field_data.get('category', ''),
            "Attribute": new_field_data.get('attribute', ''),
            "Description": new_field_data.get('description', ''),
            "Label": new_field_data.get('label', '')
        }
        
        # Create Excel file with new_suggested_fields tab - Fixed Windows file locking issue
        temp_file = None
        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
            temp_file.close()  # Close file handle to allow Excel writer to use it
            
            # Create Excel content
            with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
                # Write new_suggested_fields tab
                new_suggested_fields_df = pd.DataFrame([formatted_suggestion])
                new_suggested_fields_df.to_excel(writer, sheet_name='new_suggested_fields', index=False)
            
            # Read the file content
            with open(temp_file.name, 'rb') as f:
                excel_content = f.read()
                
        finally:
            # Clean up temp file
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except (OSError, PermissionError) as e:
                    logger.warning(f"Could not delete temporary file {temp_file.name}: {e}")
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"new_field_suggestion_{field_name.replace(' ', '_')}_{timestamp}.xlsx"
        
        return StreamingResponse(
            io.BytesIO(excel_content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading single field suggestion: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to download field suggestion: {str(e)}"
        )

@router.delete(
    "/session/{session_id}",
    summary="Clear Session",
    description="Clear the session and clean the slate - user can exit at any time",
    status_code=status.HTTP_200_OK
)
async def clear_session(session_id: str, token: str = Depends(token_dependency)):
    """Clear the session and clean the slate"""
    try:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is required.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if session_id in processing_sessions:
            # Clean up the session
            del processing_sessions[session_id]
            logger.info(f"Session {session_id} cleared successfully")
            
            return {
                'session_id': session_id,
                'status': 'cleared',
                'message': 'Session cleared successfully. You can now start a new session.'
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to clear session: {str(e)}"
        )

@router.get(
    "/session/{session_id}/status",
    summary="Get Session Status",
    description="Get the current status of the processing session",
    status_code=status.HTTP_200_OK
)
async def get_session_status(session_id: str, token: str = Depends(token_dependency)):
    """Get the current status of the processing session"""
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
        batch_size = session['bulk_batch_size']
        
        # Calculate current batch info
        current_batch_start = (session['current_index'] // batch_size) * batch_size
        current_batch_end = min(current_batch_start + batch_size, len(session['processable_indices']))
        
        # Count processed fields in current batch
        processed_in_batch = 0
        for i in range(current_batch_start, min(session['current_index'], current_batch_end)):
            df_index = session['processable_indices'][i]
            field_row = session['original_df'][df_index]
            field_name = field_row[StandardFieldHeaders.FIELD_NAME.value]
            if field_name in session['bulk_results_cache']:
                processed_in_batch += 1
        
        return {
            'session_id': session_id,
            'status': session['status'],
            'created_at': session['created_at'].isoformat(),
            'last_updated': session['last_updated'].isoformat(),
            'progress': {
                'total_fields': session['total_fields'],
                'processable_fields': session['processable_fields'],
                'processed_fields': session['processed_fields'],
                'current_index': session['current_index'],
                'remaining_fields': session['processable_fields'] - session['processed_fields']
            },
            'batch_info': {
                'batch_size': batch_size,
                'current_batch_start': current_batch_start,
                'current_batch_end': current_batch_end,
                'processed_in_current_batch': processed_in_batch,
                'total_batches': (len(session['processable_indices']) + batch_size - 1) // batch_size,
                'current_batch_number': (session['current_index'] // batch_size) + 1
            },
            'new_field_suggestions_count': len(session['new_field_suggestions']),
            'can_download': session['processed_fields'] > 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to get session status: {str(e)}"
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