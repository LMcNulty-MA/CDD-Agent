"""
Web Interface Router

This router provides endpoints for the web-based CDD mapping interface,
focusing on single field checking functionality.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
import pandas as pd
import io

from app.core.models import (
    SingleFieldCheckRequest, SingleFieldCheckResponse,
    StandardFieldHeaders
)
from app.core.services import cdd_mapping_service
from app.core.security import oauth2_scheme
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

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
        logger.info(f"Checking field: {request.field_name}")
        
        # Validate token is present (oauth2_scheme should handle this, but double-check)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is required. Please provide a valid Bearer token in the Authorization header.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Use the service to check the field
        result = cdd_mapping_service.check_single_field(
            request.field_name, 
            request.field_definition,
            force_new_suggestion=request.force_new_suggestion or False,
            feedback_history=request.feedback_history
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
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CDD Field Mapping Tool</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                color: #333;
                transition: all 0.3s ease;
            }
            
            /* Theme toggle button (same as Swagger UI) */
            .theme-switch-container {
                position: fixed;
                top: 10px;
                right: 20px;
                z-index: 1000;
                display: flex;
                align-items: center;
            }
            .theme-switch-label {
                margin-right: 10px;
                color: #fff;
                font-weight: 500;
                font-size: 14px;
            }
            .theme-switch {
                position: relative;
                display: inline-block;
                width: 60px;
                height: 34px;
            }
            .theme-switch input {
                opacity: 0;
                width: 0;
                height: 0;
            }
            .slider {
                position: absolute;
                cursor: pointer;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: #ccc;
                transition: .4s;
                border-radius: 34px;
            }
            .slider:before {
                position: absolute;
                content: "";
                height: 26px;
                width: 26px;
                left: 4px;
                bottom: 4px;
                background-color: white;
                transition: .4s;
                border-radius: 50%;
            }
            input:checked + .slider {
                background-color: #2196F3;
            }
            input:checked + .slider:before {
                transform: translateX(26px);
            }
            
            /* Dark theme styles */
            body.dark-theme {
                background: linear-gradient(135deg, #1e1e1e 0%, #2d2d2d 100%);
                color: #ffffff;
            }
            
            .dark-theme .theme-switch-label {
                color: #ffffff;
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }
            
            .header {
                text-align: center;
                color: white;
                margin-bottom: 30px;
            }
            
            .header h1 {
                font-size: 2.5rem;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            
            .header p {
                font-size: 1.1rem;
                opacity: 0.9;
            }
            
            .card {
                background: white;
                border-radius: 15px;
                padding: 30px;
                margin-bottom: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                transition: all 0.3s ease;
            }
            
            .card:hover {
                transform: translateY(-5px);
            }
            
            .dark-theme .card {
                background: #252526;
                border: 1px solid #444444;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }
            
            .dark-theme .header h1,
            .dark-theme .header p {
                color: #ffffff;
            }
            
            .auth-section {
                margin-bottom: 30px;
            }
            
            .auth-section h2 {
                color: #4a5568;
                margin-bottom: 15px;
                display: flex;
                align-items: center;
            }
            
            .auth-section h2::before {
                content: "🔐";
                margin-right: 10px;
            }
            
            .form-group {
                margin-bottom: 20px;
            }
            
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 600;
                color: #4a5568;
            }
            
            .form-group input, .form-group textarea, .form-group select {
                width: 100%;
                padding: 12px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 14px;
                transition: border-color 0.3s ease;
            }
            
            .form-group input:focus, .form-group textarea:focus, .form-group select:focus {
                outline: none;
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }
            
            .dark-theme .auth-section h2,
            .dark-theme .form-group label {
                color: #ffffff;
            }
            
            .dark-theme .form-group input,
            .dark-theme .form-group textarea,
            .dark-theme .form-group select {
                background-color: #2d2d2d;
                color: #ffffff;
                border-color: #444444;
            }
            
            .dark-theme .form-group input:focus,
            .dark-theme .form-group textarea:focus,
            .dark-theme .form-group select:focus {
                border-color: #2196F3;
                box-shadow: 0 0 0 3px rgba(33, 150, 243, 0.1);
            }
            
            .btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.3s ease;
                text-decoration: none;
                display: inline-block;
                margin-right: 10px;
                margin-bottom: 10px;
            }
            
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            }
            
            .btn-secondary {
                background: #718096;
            }
            
            .btn-success {
                background: #48bb78;
            }
            
            .btn-danger {
                background: #f56565;
            }
            
            .match-item {
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 15px;
                margin-bottom: 10px;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            .match-item:hover {
                border-color: #667eea;
                background: #f0f4ff;
            }
            
            .match-item.selected {
                border-color: #667eea;
                background: #e6fffa;
            }
            
            .dark-theme .match-item {
                background: #1a1a1a;
                border-color: #444444;
                color: #ffffff;
            }
            
            .dark-theme .match-item:hover {
                border-color: #2196F3;
                background: #2d2d2d;
            }
            
            .dark-theme .match-item.selected {
                border-color: #2196F3;
                background: #1e3a5f;
            }
            
            /* Alert styles */
            .alert {
                padding: 15px;
                margin: 10px 0;
                border-radius: 6px;
                border: 1px solid transparent;
            }
            
            .alert-success {
                background-color: #d4edda;
                border-color: #c3e6cb;
                color: #155724;
            }
            
            .alert-error {
                background-color: #f8d7da;
                border-color: #f5c6cb;
                color: #721c24;
            }
            
            .alert-info {
                background-color: #d1ecf1;
                border-color: #bee5eb;
                color: #0c5460;
            }
            
            .dark-theme .alert-success {
                background-color: #1e3a2e;
                border-color: #2d5a3d;
                color: #4ade80;
            }
            
            .dark-theme .alert-error {
                background-color: #3a1e1e;
                border-color: #5a2d2d;
                color: #f87171;
            }
            
            .dark-theme .alert-info {
                background-color: #1e2a3a;
                border-color: #2d3d5a;
                color: #60a5fa;
            }
            
            /* Match item styling */
            .match-meta {
                color: #718096;
            }
            
            .match-description {
                color: #4a5568;
            }
            
            .dark-theme .match-meta {
                color: #a0aec0;
            }
            
            .dark-theme .match-description {
                color: #e2e8f0;
            }
            
            /* New field suggestion styling */
            .suggestion-container {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 20px;
                margin-top: 15px;
                background: #f7fafc;
            }
            
            .dark-theme .suggestion-container {
                background: #2d2d2d;
                border-color: #444444;
            }
            
            .suggestion-field {
                margin-bottom: 10px;
                font-size: 14px;
            }
            
            .suggestion-field strong {
                color: #2d3748;
            }
            
            .dark-theme .suggestion-field strong {
                color: #e2e8f0;
            }
            
            .suggestion-field .field-value {
                color: #4a5568;
            }
            
            .dark-theme .suggestion-field .field-value {
                color: #a0aec0;
            }
            
            .dark-theme .suggestion-container > div:last-child {
                border-top-color: #444444 !important;
            }
            
            /* Generate new field section styling */
            .generate-new-section {
                background: #f8f9fa;
                border-left: 4px solid #667eea;
            }
            
            .dark-theme .generate-new-section {
                background: #2d2d2d;
                border-left-color: #2196F3;
            }
            
            .dark-theme .generate-new-section p {
                color: #a0aec0 !important;
            }
            
            /* Modal styling */
            .modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                z-index: 1000;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .modal-content {
                background: white;
                padding: 30px;
                border-radius: 12px;
                max-width: 600px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
            }
            
            .modal-header {
                margin-top: 0;
                color: #2d3748;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .modal-description {
                color: #4a5568;
                margin-bottom: 20px;
                line-height: 1.5;
            }
            
            .modal-textarea {
                width: 100%;
                padding: 12px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 14px;
                resize: vertical;
                font-family: inherit;
                transition: border-color 0.3s ease;
            }
            
            .modal-textarea:focus {
                outline: none;
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }
            
            .modal-footer {
                margin-top: 20px;
                text-align: right;
                display: flex;
                gap: 10px;
                justify-content: flex-end;
            }
            
            .modal-btn {
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.3s ease;
            }
            
            .modal-btn-cancel {
                background: #718096;
                color: white;
            }
            
            .modal-btn-cancel:hover {
                background: #4a5568;
            }
            
            .modal-btn-submit {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            
            .modal-btn-submit:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
            }
            
            /* Dark mode modal styling */
            .dark-theme .modal-overlay {
                background: rgba(0, 0, 0, 0.7);
            }
            
            .dark-theme .modal-content {
                background: #2d2d2d;
                color: #ffffff;
                border: 1px solid #444444;
            }
            
            .dark-theme .modal-header {
                color: #ffffff;
            }
            
            .dark-theme .modal-description {
                color: #a0aec0;
            }
            
            .dark-theme .modal-textarea {
                background: #1a1a1a;
                color: #ffffff;
                border-color: #444444;
            }
            
            .dark-theme .modal-textarea:focus {
                border-color: #2196F3;
                box-shadow: 0 0 0 3px rgba(33, 150, 243, 0.1);
            }
            
            .dark-theme .modal-btn-cancel {
                background: #4a5568;
                color: #ffffff;
            }
            
            .dark-theme .modal-btn-cancel:hover {
                background: #2d3748;
            }
            
            .confidence-score {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 600;
                color: white;
            }
            
            .confidence-high { background: #48bb78; }
            .confidence-medium { background: #ed8936; }
            .confidence-low { background: #f56565; }
            
            .hidden {
                display: none !important;
            }
            
            .alert {
                padding: 12px;
                border-radius: 6px;
                margin-bottom: 15px;
            }
            
            .alert-success {
                background: #c6f6d5;
                color: #22543d;
                border: 1px solid #9ae6b4;
            }
            
            .alert-error {
                background: #fed7d7;
                color: #742a2a;
                border: 1px solid #fc8181;
            }
            
            .alert-info {
                background: #bee3f8;
                color: #2a4365;
                border: 1px solid #90cdf4;
            }
            
            .loading {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 3px solid #f3f3f3;
                border-top: 3px solid #667eea;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div class="theme-switch-container">
            <span class="theme-switch-label">Dark Mode</span>
            <label class="theme-switch">
                <input type="checkbox" id="theme-toggle">
                <span class="slider"></span>
            </label>
        </div>
        
        <div class="container">
            <div class="header">
                <h1>🎯 CDD Field Mapping Tool</h1>
                <p>Intelligent mapping of your fields to Common Data Dictionary attributes</p>
            </div>
            
            <!-- Authentication Section -->
            <div class="card auth-section">
                <h2>Authentication</h2>
                <div class="form-group">
                    <label for="authToken">Authentication Token:</label>
                    <input type="password" id="authToken" placeholder="Enter your authentication token">
                </div>
                <button class="btn" onclick="authenticateUser()">
                    <span id="authLoadingIcon" class="loading hidden"></span>
                    Authenticate
                </button>
                <div id="authStatus" class="hidden"></div>
            </div>
            
            <!-- Main Interface (hidden until authenticated) -->
            <div id="mainInterface" class="hidden">
                <div class="card">
                    <h2>🔍 Check Single Field</h2>
                    <p style="margin-bottom: 20px; color: #718096;">
                        Test a single field against the CDD database to see potential matches or get suggestions for new fields.
                        <br><a href="#" onclick="downloadExampleFile('csv')" style="color: #667eea;">Download CSV example</a> | 
                        <a href="#" onclick="downloadExampleFile('json')" style="color: #667eea;">Download JSON example</a>
                    </p>
                    
                    <div class="form-group">
                        <label for="fieldName">Field Name:</label>
                        <input type="text" id="fieldName" placeholder="e.g., LoanAmount, InterestRate">
                    </div>
                    
                    <div class="form-group">
                        <label for="fieldDefinition">Field Definition/Description:</label>
                        <textarea id="fieldDefinition" rows="3" placeholder="Describe what this field represents..."></textarea>
                    </div>
                    
                    <button class="btn" onclick="checkSingleField()">
                        <span id="singleCheckLoadingIcon" class="loading hidden"></span>
                        Check Field
                    </button>
                    
                    <div id="singleFieldStatus" class="alert hidden"></div>
                    
                    <div id="singleFieldResults" class="hidden">
                        <h3>Results:</h3>
                        <div id="singleFieldContent"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            // Global variables
            let authToken = '';
            
            // Theme toggle functionality (same as Swagger UI)
            const themeToggle = document.getElementById('theme-toggle');
            
            // Check for saved theme preference or prefer-color-scheme
            const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');
            const savedTheme = localStorage.getItem('cdd-agent-web-theme');
            
            if (savedTheme === 'dark' || (!savedTheme && prefersDarkScheme.matches)) {
                document.body.classList.add('dark-theme');
                themeToggle.checked = true;
            }
            
            // Add toggle event
            themeToggle.addEventListener('change', function() {
                if (this.checked) {
                    document.body.classList.add('dark-theme');
                    localStorage.setItem('cdd-agent-web-theme', 'dark');
                } else {
                    document.body.classList.remove('dark-theme');
                    localStorage.setItem('cdd-agent-web-theme', 'light');
                }
            });
            
            // Listen for system theme changes
            prefersDarkScheme.addEventListener('change', function(e) {
                const savedTheme = localStorage.getItem('cdd-agent-web-theme');
                if (!savedTheme) {
                    if (e.matches) {
                        document.body.classList.add('dark-theme');
                        themeToggle.checked = true;
                    } else {
                        document.body.classList.remove('dark-theme');
                        themeToggle.checked = false;
                    }
                }
            });
            
            // Authentication
            async function authenticateUser() {
                const token = document.getElementById('authToken').value.trim();
                if (!token) {
                    showAlert('authStatus', 'Please enter an authentication token', 'error');
                    return;
                }
                
                showLoading('authLoadingIcon', true);
                
                try {
                    // Test authentication by making a simple API call
                    const response = await fetch('/cdd-agent/categories', {
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });
                    
                    if (response.ok) {
                        authToken = token;
                        showAlert('authStatus', 'Authentication successful!', 'success');
                        document.getElementById('mainInterface').classList.remove('hidden');
                    } else {
                        const errorData = await response.json().catch(() => ({}));
                        let errorMessage = 'Authentication failed';
                        
                        if (response.status === 401 || response.status === 403) {
                            errorMessage = 'Invalid authentication token. Please check your token and try again.';
                        } else if (errorData.detail) {
                            errorMessage = errorData.detail;
                        } else if (response.status === 422) {
                            errorMessage = 'There was an issue with your request. Please try again.';
                        }
                        
                        showAlert('authStatus', errorMessage, 'error');
                    }
                } catch (error) {
                    console.error('Authentication error:', error);
                    showAlert('authStatus', 'Unable to connect to the server. Please check your connection and try again.', 'error');
                }
                
                showLoading('authLoadingIcon', false);
            }
            
            // Single field check
            async function checkSingleField() {
                const fieldName = document.getElementById('fieldName').value.trim();
                const fieldDefinition = document.getElementById('fieldDefinition').value.trim();
                
                if (!fieldName || !fieldDefinition) {
                    showAlert('singleFieldStatus', 'Please enter both field name and definition', 'error');
                    return;
                }
                
                showLoading('singleCheckLoadingIcon', true);
                
                try {
                    const response = await fetch('/cdd-agent/web/check-field', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${authToken}`
                        },
                        body: JSON.stringify({
                            field_name: fieldName,
                            field_definition: fieldDefinition
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (response.ok) {
                        displaySingleFieldResults(result);
                    } else {
                        let errorMessage = 'An error occurred while checking the field';
                        
                        if (response.status === 401 || response.status === 403) {
                            errorMessage = 'Authentication expired. Please re-authenticate and try again.';
                            // Hide main interface and show auth section
                            document.getElementById('mainInterface').classList.add('hidden');
                            authToken = null;
                        } else if (result.detail) {
                            errorMessage = result.detail;
                        }
                        
                        showAlert('singleFieldStatus', errorMessage, 'error');
                    }
                } catch (error) {
                    console.error('Field check error:', error);
                    showAlert('singleFieldStatus', 'Unable to connect to the server. Please check your connection and try again.', 'error');
                }
                
                showLoading('singleCheckLoadingIcon', false);
            }
            
            function displaySingleFieldResults(result) {
                const resultsDiv = document.getElementById('singleFieldResults');
                const contentDiv = document.getElementById('singleFieldContent');
                
                let html = `
                    <div class="alert alert-info">
                        <strong>Status:</strong> ${result.status} 
                        (Confidence threshold: ${result.confidence_threshold})
                    </div>
                `;
                
                if (result.matches && result.matches.length > 0) {
                    html += '<h4>🎯 Potential Matches:</h4>';
                    html += '<div style="max-height: 400px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; margin-bottom: 20px;">';
                    result.matches.forEach(match => {
                        const confidenceClass = match.confidence_score >= 0.8 ? 'confidence-high' : 
                                               match.confidence_score >= 0.6 ? 'confidence-medium' : 'confidence-low';
                        
                        html += `
                            <div class="match-item" style="margin-bottom: 15px; padding: 15px; border: 1px solid #e2e8f0; border-radius: 6px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                    <strong style="word-break: break-word; flex: 1; margin-right: 10px;">${match.cdd_field}</strong>
                                    <span class="confidence-score ${confidenceClass}" style="flex-shrink: 0;">
                                        ${Math.round(match.confidence_score * 100)}%
                                    </span>
                                </div>
                                <div class="match-meta" style="margin-bottom: 8px; font-size: 14px;">
                                    <strong>Category:</strong> ${match.category || 'N/A'} | 
                                    <strong>Type:</strong> ${match.data_type || 'N/A'}
                                </div>
                                <div class="match-description" style="font-size: 14px; line-height: 1.4; word-wrap: break-word;">
                                    ${match.description || 'No description available'}
                                </div>
                            </div>
                        `;
                    });
                    html += '</div>';
                    
                    // Add "Generate New Field" button if there are matches but user might not like them
                    html += `
                        <div class="generate-new-section" style="margin-top: 15px; padding: 15px; border-radius: 8px;">
                            <p style="margin: 0 0 10px 0; color: #4a5568; font-size: 14px;">
                                Don't see a good match? Generate a new CDD field suggestion instead.
                            </p>
                            <button class="btn generate-new-field-btn" data-field-name="${result.field_name}" data-field-definition="${btoa(result.field_definition)}">
                                💡 Generate New Field
                            </button>
                        </div>
                    `;
                }
                
                if (result.new_field_suggestion) {
                    const suggestion = result.new_field_suggestion;
                    html += `
                        <h4>💡 New Field Suggestion:</h4>
                        <div class="suggestion-container">
                            <div class="suggestion-field">
                                <strong>Suggested Name:</strong> <span class="field-value">${suggestion.attribute}</span>
                            </div>
                            <div class="suggestion-field">
                                <strong>Category:</strong> <span class="field-value">${suggestion.category}</span> | 
                                <strong>Type:</strong> <span class="field-value">${suggestion.data_type}</span>
                            </div>
                            <div class="suggestion-field">
                                <strong>Label:</strong> <span class="field-value">${suggestion.label}</span>
                            </div>
                            <div class="suggestion-field">
                                <strong>Description:</strong> <span class="field-value">${suggestion.description}</span>
                            </div>
                            <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e2e8f0;">
                                <button class="btn btn-success" onclick="downloadSuggestion('csv', '${suggestion.attribute}', '${suggestion.category}', '${suggestion.data_type}', '${suggestion.label}', '${suggestion.description.replace(/'/g, "\\'")}')">
                                    📄 Download CSV
                                </button>
                                <button class="btn btn-success" onclick="downloadSuggestion('json', '${suggestion.attribute}', '${suggestion.category}', '${suggestion.data_type}', '${suggestion.label}', '${suggestion.description.replace(/'/g, "\\'")}')">
                                    📋 Download JSON
                                </button>
                                <button class="btn btn-secondary provide-feedback-btn" data-field-name="${result.field_name}" data-field-definition="${btoa(result.field_definition)}">
                                    🔄 Provide Feedback & Regenerate
                                </button>
                            </div>
                        </div>
                    `;
                }
                
                contentDiv.innerHTML = html;
                resultsDiv.classList.remove('hidden');
                
                // Add event listeners for the new buttons
                const generateNewBtn = contentDiv.querySelector('.generate-new-field-btn');
                if (generateNewBtn) {
                    generateNewBtn.addEventListener('click', function() {
                        const fieldName = this.getAttribute('data-field-name');
                        const fieldDefinition = atob(this.getAttribute('data-field-definition'));
                        generateNewFieldFromMatches(fieldName, fieldDefinition);
                    });
                }
                
                const provideFeedbackBtn = contentDiv.querySelector('.provide-feedback-btn');
                if (provideFeedbackBtn) {
                    provideFeedbackBtn.addEventListener('click', function() {
                        const fieldName = this.getAttribute('data-field-name');
                        const fieldDefinition = atob(this.getAttribute('data-field-definition'));
                        provideFeedback(fieldName, fieldDefinition);
                    });
                }
            }
            
            async function downloadExampleFile(format) {
                try {
                    const response = await fetch(`/cdd-agent/web/example-file?format=${format}`, {
                        headers: {
                            'Authorization': `Bearer ${authToken}`
                        }
                    });
                    
                    if (response.ok) {
                        const blob = await response.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `example_cdd_mapping.${format}`;
                        document.body.appendChild(a);
                        a.click();
                        window.URL.revokeObjectURL(url);
                        document.body.removeChild(a);
                    } else {
                        const errorData = await response.json().catch(() => ({}));
                        let errorMessage = 'Failed to download example file';
                        
                        if (response.status === 401 || response.status === 403) {
                            errorMessage = 'Authentication expired. Please re-authenticate and try again.';
                            document.getElementById('mainInterface').classList.add('hidden');
                            authToken = null;
                        } else if (errorData.detail) {
                            errorMessage = errorData.detail;
                        }
                        
                        showAlert('singleFieldStatus', errorMessage, 'error');
                    }
                } catch (error) {
                    console.error('Download error:', error);
                    showAlert('singleFieldStatus', 'Unable to download file. Please check your connection and try again.', 'error');
                }
            }
            
            // Utility functions
            function showLoading(elementId, show) {
                const element = document.getElementById(elementId);
                if (show) {
                    element.classList.remove('hidden');
                } else {
                    element.classList.add('hidden');
                }
            }
            
            function showAlert(elementId, message, type) {
                const element = document.getElementById(elementId);
                element.className = `alert alert-${type}`;
                element.innerHTML = message;
                element.classList.remove('hidden');
            }
            
            function downloadSuggestion(format, attribute, category, dataType, label, description) {
                try {
                    // Create the suggestion data in the exact format of ZM_New_CDD_Field_Requests.csv
                    const suggestionData = {
                        Category: category,
                        Attribute: attribute,
                        Description: description,
                        Label: label,
                        Tag: "", // Leave empty as requested
                        "New - Update - Deprecate (NOTE: ALWAYS NEW FOR NOW)": "New",
                        "Partition Key Order (NOTE: LEAVE EMPTY FOR NOW)": "",
                        "Index Key (NOTE: LEAVE EMPTY FOR NOW)": ""
                    };
                    
                    let content, filename, mimeType;
                    
                    if (format === 'csv') {
                        // Create CSV format matching ZM_New_CDD_Field_Requests.csv exactly
                        const headers = [
                            'Category',
                            'Attribute', 
                            'Description',
                            'Label',
                            'Tag',
                            'New - Update - Deprecate (NOTE: ALWAYS NEW FOR NOW)',
                            'Partition Key Order (NOTE: LEAVE EMPTY FOR NOW)',
                            'Index Key (NOTE: LEAVE EMPTY FOR NOW)'
                        ];
                        const values = [
                            suggestionData.Category,
                            suggestionData.Attribute,
                            `"${suggestionData.Description.replace(/"/g, '""')}"`, // Escape quotes in CSV
                            suggestionData.Label,
                            suggestionData.Tag,
                            suggestionData["New - Update - Deprecate (NOTE: ALWAYS NEW FOR NOW)"],
                            suggestionData["Partition Key Order (NOTE: LEAVE EMPTY FOR NOW)"],
                            suggestionData["Index Key (NOTE: LEAVE EMPTY FOR NOW)"]
                        ];
                        content = headers.join(',') + '\\n' + values.join(',');
                        filename = `ZM_New_CDD_Field_Request_${attribute}.csv`;
                        mimeType = 'text/csv';
                    } else {
                        // Create JSON format
                        content = JSON.stringify([suggestionData], null, 2);
                        filename = `ZM_New_CDD_Field_Request_${attribute}.json`;
                        mimeType = 'application/json';
                    }
                    
                    // Create and trigger download
                    const blob = new Blob([content], { type: mimeType });
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                    
                    showAlert('singleFieldStatus', `${format.toUpperCase()} file downloaded successfully!`, 'success');
                    
                } catch (error) {
                    console.error('Download error:', error);
                    showAlert('singleFieldStatus', 'Failed to download suggestion file. Please try again.', 'error');
                }
            }
            
            // Global variable to track conversation history
            let conversationHistory = [];
            
            // Theme utility functions
            function isDarkMode() {
                return document.body.classList.contains('dark-theme');
            }
            
            function applyThemeToElement(element, lightStyles, darkStyles) {
                if (isDarkMode()) {
                    Object.assign(element.style, darkStyles);
                } else {
                    Object.assign(element.style, lightStyles);
                }
            }
            
            async function generateNewFieldFromMatches(fieldName, fieldDefinition) {
                console.log('generateNewFieldFromMatches called with:', fieldName, fieldDefinition);
                
                // Clear any existing results and show loading
                document.getElementById('singleFieldResults').classList.add('hidden');
                showLoading('singleCheckLoadingIcon', true);
                
                try {
                    const response = await fetch('/cdd-agent/web/check-field', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${authToken}`
                        },
                        body: JSON.stringify({
                            field_name: fieldName,
                            field_definition: fieldDefinition,
                            force_new_suggestion: true // Flag to force new field generation
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (response.ok) {
                        // Add to conversation history
                        conversationHistory.push({
                            action: 'generate_new_field',
                            field_name: fieldName,
                            field_definition: fieldDefinition,
                            timestamp: new Date().toISOString()
                        });
                        
                        displaySingleFieldResults(result);
                    } else {
                        let errorMessage = 'An error occurred while generating new field';
                        if (response.status === 401 || response.status === 403) {
                            errorMessage = 'Authentication expired. Please re-authenticate and try again.';
                            document.getElementById('mainInterface').classList.add('hidden');
                            authToken = null;
                        } else if (result.detail) {
                            errorMessage = result.detail;
                        }
                        showAlert('singleFieldStatus', errorMessage, 'error');
                    }
                } catch (error) {
                    console.error('Generate new field error:', error);
                    showAlert('singleFieldStatus', 'Unable to generate new field. Please check your connection and try again.', 'error');
                }
                
                showLoading('singleCheckLoadingIcon', false);
            }
            
            function provideFeedback(fieldName, fieldDefinition) {
                // Create feedback modal with proper CSS classes
                const modal = document.createElement('div');
                modal.className = 'modal-overlay';
                
                modal.innerHTML = `
                    <div class="modal-content">
                        <h3 class="modal-header">💬 Provide Feedback</h3>
                        <p class="modal-description">
                            What would you like to change about the suggested field? Be specific about what you'd like to see different.
                        </p>
                        <textarea id="feedbackText" rows="4" class="modal-textarea" 
                            placeholder="e.g., The category should be 'entityReference' instead of 'instrumentReference', or the description should be more specific about the calculation method..."></textarea>
                        <div class="modal-footer">
                            <button class="modal-btn modal-btn-cancel">
                                Cancel
                            </button>
                            <button class="modal-btn modal-btn-submit" data-field-name="${fieldName}" data-field-definition="${btoa(fieldDefinition)}">
                                Submit Feedback & Regenerate
                            </button>
                        </div>
                    </div>
                `;
                
                // Add event listeners for buttons
                const submitBtn = modal.querySelector('.modal-btn-submit');
                const cancelBtn = modal.querySelector('.modal-btn-cancel');
                
                submitBtn.addEventListener('click', function() {
                    const fieldName = this.getAttribute('data-field-name');
                    const fieldDefinition = atob(this.getAttribute('data-field-definition'));
                    console.log('Submit button clicked:', fieldName, fieldDefinition); // Debug log
                    submitFeedback(fieldName, fieldDefinition, modal);
                });
                
                cancelBtn.addEventListener('click', function() {
                    console.log('Cancel button clicked'); // Debug log
                    document.removeEventListener('keydown', handleKeyDown);
                    modal.remove();
                });
                
                // Also allow clicking outside to close
                modal.addEventListener('click', function(e) {
                    if (e.target === modal) {
                        console.log('Clicked outside modal'); // Debug log
                        document.removeEventListener('keydown', handleKeyDown);
                        modal.remove();
                    }
                });
                
                // Add keyboard support
                const handleKeyDown = function(e) {
                    if (e.key === 'Escape') {
                        console.log('Escape key pressed'); // Debug log
                        document.removeEventListener('keydown', handleKeyDown);
                        modal.remove();
                    }
                };
                modal.handleKeyDown = handleKeyDown; // Store reference for cleanup
                document.addEventListener('keydown', handleKeyDown);
                
                document.body.appendChild(modal);
                modal.querySelector('textarea').focus();
            }
            
            async function submitFeedback(fieldName, fieldDefinition, modal) {
                const feedbackText = modal.querySelector('#feedbackText').value.trim();
                if (!feedbackText) {
                    showAlert('singleFieldStatus', 'Please provide feedback before submitting.', 'error');
                    return;
                }
                
                console.log('Submitting feedback:', feedbackText); // Debug log
                
                // Add feedback to conversation history
                conversationHistory.push({
                    action: 'feedback',
                    field_name: fieldName,
                    field_definition: fieldDefinition,
                    feedback: feedbackText,
                    timestamp: new Date().toISOString()
                });
                
                // Close modal and clean up event listeners
                document.removeEventListener('keydown', modal.handleKeyDown);
                modal.remove();
                
                // Show loading
                document.getElementById('singleFieldResults').classList.add('hidden');
                showLoading('singleCheckLoadingIcon', true);
                
                try {
                    const response = await fetch('/cdd-agent/web/check-field', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${authToken}`
                        },
                        body: JSON.stringify({
                            field_name: fieldName,
                            field_definition: fieldDefinition,
                            force_new_suggestion: true,
                            feedback_history: conversationHistory
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (response.ok) {
                        displaySingleFieldResults(result);
                        showAlert('singleFieldStatus', 'New suggestion generated based on your feedback!', 'success');
                    } else {
                        let errorMessage = 'An error occurred while processing feedback';
                        if (response.status === 401 || response.status === 403) {
                            errorMessage = 'Authentication expired. Please re-authenticate and try again.';
                            document.getElementById('mainInterface').classList.add('hidden');
                            authToken = null;
                        } else if (result.detail) {
                            errorMessage = result.detail;
                        }
                        showAlert('singleFieldStatus', errorMessage, 'error');
                    }
                } catch (error) {
                    console.error('Feedback submission error:', error);
                    showAlert('singleFieldStatus', 'Unable to process feedback. Please check your connection and try again.', 'error');
                }
                
                showLoading('singleCheckLoadingIcon', false);
            }
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content) 