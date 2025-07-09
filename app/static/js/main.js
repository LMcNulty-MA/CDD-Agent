// Global variables
let authToken = null;
let currentSessionId = null;
let selectedFile = null;
let currentMatches = [];
let currentNewFieldSuggestion = null;
let feedbackHistory = [];
let currentSingleFieldResult = null;
let isProcessingField = false;  // Prevent rapid field processing
let lastProcessTime = 0;        // Track timing for rate limiting
let currentFieldData = null;    // Store current field data for processing
let batchSize = 5;              // Batch size for bulk processing (updated from server)

// Global error handler for API responses
async function handleApiResponse(response, operation = 'API call') {
    if (response.status === 401) {
        // Token expired or invalid
        console.log('Token expired, clearing authentication');
        authToken = null;
        localStorage.removeItem('cdd_auth_token');
        
        // Hide main interface and show auth interface
        document.getElementById('mainInterface').classList.add('hidden');
        document.getElementById('authToken').value = '';
        
        // Show user-friendly message
        showAlert('authStatus', 'Your session has expired. Please enter your authentication token again.', 'error');
        
        // Clear any ongoing sessions
        currentSessionId = null;
        
        // Reset processing state
        lastBulkProcessedIndex = -1;
        
        throw new Error('Authentication expired');
    }
    
    if (!response.ok) {
        let errorMessage = `${operation} failed`;
        try {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorData.message || errorMessage;
        } catch (e) {
            // If we can't parse error response, use generic message
            errorMessage = `${operation} failed (${response.status}: ${response.statusText})`;
        }
        throw new Error(errorMessage);
    }
    
    return response;
}

// Initialize page on load
document.addEventListener('DOMContentLoaded', function() {
    // Load saved token from localStorage
    const savedToken = localStorage.getItem('cdd_auth_token');
    if (savedToken) {
        authToken = savedToken;
        document.getElementById('authToken').value = savedToken;
        // Automatically show main interface if token exists
        document.getElementById('mainInterface').classList.remove('hidden');
        showAlert('authStatus', 'Authentication token loaded from previous session', 'success');
    }
    
    // Initialize theme
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-theme');
        document.getElementById('theme-toggle').checked = true;
    }
    
    // Theme toggle event listener
    document.getElementById('theme-toggle').addEventListener('change', function(e) {
        if (e.target.checked) {
            document.body.classList.add('dark-theme');
            localStorage.setItem('theme', 'dark');
        } else {
            document.body.classList.remove('dark-theme');
            localStorage.setItem('theme', 'light');
        }
    });
});

// Theme toggle functionality
document.addEventListener('DOMContentLoaded', function() {
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
});

// Utility functions
function showLoading(elementId, show) {
    const element = document.getElementById(elementId);
    if (element) {
        if (show) {
            element.classList.remove('hidden');
        } else {
            element.classList.add('hidden');
        }
    }
}

function showAlert(elementId, message, type) {
    const element = document.getElementById(elementId);
    if (element) {
        // Check if this is an inline alert
        if (element.classList.contains('inline-alert')) {
            element.className = `inline-alert alert-${type}`;
        } else {
            element.className = `alert alert-${type}`;
        }
        element.innerHTML = message;
        element.classList.remove('hidden');
    }
}

function hideElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.classList.add('hidden');
    }
}

function showElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.classList.remove('hidden');
    }
}

function disableAllInteraction() {
    const buttons = document.querySelectorAll('button:not([disabled])');
    buttons.forEach(btn => {
        btn.disabled = true;
        btn.dataset.wasDisabled = 'false';
    });
}

function enableAllInteraction() {
    const buttons = document.querySelectorAll('button[disabled]');
    buttons.forEach(btn => {
        if (btn.dataset.wasDisabled !== 'true') {
            btn.disabled = false;
        }
    });
}

// Authentication
async function authenticateUser() {
    const tokenInput = document.getElementById('authToken').value.trim();
    
    if (!tokenInput) {
        showAlert('authStatus', 'Please enter your authentication token', 'error');
        return;
    }
    
    showLoading('authLoadingIcon', true);
    
    try {
        // Test the token by making a request to the categories endpoint
        const response = await fetch('/cdd-agent/categories', {
            headers: {
                'Authorization': `Bearer ${tokenInput}`
            }
        });
        
        await handleApiResponse(response, 'Authentication');
        
        authToken = tokenInput;
        // Save token to localStorage
        localStorage.setItem('cdd_auth_token', tokenInput);
        
        showAlert('authStatus', 'Authentication successful! 🎉', 'success');
        document.getElementById('mainInterface').classList.remove('hidden');
        
    } catch (error) {
        console.error('Authentication error:', error);
        // Clear saved token on error
        localStorage.removeItem('cdd_auth_token');
        
        if (error.message === 'Authentication expired') {
            showAlert('authStatus', 'Invalid token. Please check your authentication token and try again.', 'error');
        } else {
            showAlert('authStatus', 'Unable to authenticate. Please check your connection and try again.', 'error');
        }
    }
    
    showLoading('authLoadingIcon', false);
}

// File handling
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        const allowedTypes = ['.xlsx'];
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
        
        if (allowedTypes.includes(fileExtension)) {
            selectedFile = file;
            document.getElementById('uploadBtn').disabled = false;
            showAlert('uploadStatus', `Selected: ${file.name} (Excel file)`, 'info');
        } else {
            selectedFile = null;
            document.getElementById('uploadBtn').disabled = true;
            showAlert('uploadStatus', 'Please select an Excel (.xlsx) file only.', 'error');
        }
    }
}

async function uploadFile() {
    if (!selectedFile) {
        showAlert('uploadStatus', 'Please select a file first.', 'error');
        return;
    }
    
    showLoading('uploadLoadingIcon', true);
    
    try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        
        const response = await fetch('/cdd-agent/web/upload-file', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            },
            body: formData
        });
        
        await handleApiResponse(response, 'File upload');
        const result = await response.json();
        
        currentSessionId = result.session_id;
        
        // Reset state for new session
        batchSize = 5; // Default batch size, will be updated from server
        currentMatches = [];
        currentNewFieldSuggestion = null;
        currentFieldData = null;
        isProcessingField = false;
        lastProcessTime = 0;
        feedbackHistory = [];
        
        console.log('🧹 State reset for new session');
        showAlert('uploadStatus', result.message, 'success');
        
        // Hide upload section and show processing interface
        hideElement('fileUploadSection');
        showElement('processingInterface');
        
        // Start by loading the first field (which will trigger bulk processing if needed)
        await loadNextField();
        
    } catch (error) {
        console.error('Upload error:', error);
        showAlert('uploadStatus', 'Unable to upload file. Please check your connection and try again.', 'error');
    }
    
    showLoading('uploadLoadingIcon', false);
}

function selectMatch(index, retryCount = 0) {
    console.log(`🖱️ selectMatch called with index: ${index}, retryCount: ${retryCount}`);
    
    // Prevent rapid clicks - check if we're already processing
    if (isProcessingField) {
        console.log('❌ Already processing field, ignoring selectMatch');
        return;
    }
    
    // Remove previous selections
    document.querySelectorAll('.match-item').forEach(item => {
        item.classList.remove('selected');
    });
    
    // Select current match
    const matchItems = document.querySelectorAll('.match-item');
    if (matchItems[index]) {
        matchItems[index].classList.add('selected');
    }
    
    // Automatically accept the match and move to next field
    // Add a small delay to ensure UI update is complete
    console.log('✅ Auto-accepting match at index:', index);
    setTimeout(() => {
        acceptMatch(index);
    }, 100); // Small delay to ensure UI is updated
}




// Bulk field processing
async function processBulkFields() {
    console.log('🚀 Processing next batch of fields...');
    
    // Update loading message to show batch processing
    const loadingMessage = document.getElementById('loadingMessage');
    if (loadingMessage) {
        loadingMessage.textContent = `Loading next ${batchSize} fields...`;
    }
    
    showElement('loadingNextField');
    hideElement('matchesSection');
    hideElement('newFieldSection');
    
    // Clear previous state
    currentMatches = [];
    currentNewFieldSuggestion = null;
    currentFieldData = null;
    
    try {
        const response = await fetch(`/cdd-agent/web/session/${currentSessionId}/bulk-process`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: new URLSearchParams({
                feedback_text: ''
            })
        });
        
        await handleApiResponse(response, 'Bulk process fields');
        
        const data = await response.json();
        console.log('Bulk processing response:', data);
        
        showAlert('uploadStatus', 
            `✅ Processed ${data.total_processed} fields in ${data.processing_time.toFixed(2)}s`, 
            'success'
        );
        
        // Update batch size from server response
        if (data.results && data.results.length > 0) {
            batchSize = data.total_processed;
            console.log(`📊 Processed ${data.total_processed} fields in this batch`);
        }
        
        // Now load the next field
        await loadNextField();
        
    } catch (error) {
        console.error('Error in bulk processing:', error);
        showAlert('uploadStatus', 'Failed to process bulk fields: ' + error.message, 'error');
        hideElement('loadingNextField');
        
        // Fallback to single field processing
        await loadNextField();
    }
}

// Field processing
async function loadNextField() {
    console.log('⏭️ loadNextField called');
    
    // Reset loading message to generic message
    const loadingMessage = document.getElementById('loadingMessage');
    if (loadingMessage) {
        loadingMessage.textContent = 'Loading next field...';
    }
    
    showElement('loadingNextField');
    hideElement('matchesSection');
    hideElement('newFieldSection');
    
    // Clear previous state
    currentMatches = [];
    currentNewFieldSuggestion = null;
    currentFieldData = null;
    
    // Clear feedback inputs
    const bulkMatchFeedback = document.getElementById('bulkMatchFeedback');
    const bulkNewFieldFeedback = document.getElementById('bulkNewFieldFeedback');
    if (bulkMatchFeedback) bulkMatchFeedback.value = '';
    if (bulkNewFieldFeedback) bulkNewFieldFeedback.value = '';
    
    try {
        console.log('🔄 Fetching next field for session:', currentSessionId);
        
        const response = await fetch(`/cdd-agent/web/session/${currentSessionId}/next-field`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        await handleApiResponse(response, 'Load next field');
        const data = await response.json();
        console.log('📥 Next field response:', data);
        
        if (data.status === 'completed') {
            // Session completed - ensure progress shows full completion
            console.log('🎉 Session completed, showing results');
            console.log('Completion progress data:', data.progress);
            
            // Force completion progress to show x/x regardless of backend numbers
            if (data.progress && data.progress.total) {
                console.log('Setting completion progress to:', data.progress.total, '/', data.progress.total);
                updateProgressBar(data.progress.total, data.progress.total);
            }
            
            showElement('sessionCompleted');
            hideElement('currentFieldSection');
            return;
        }
        
        // Store current field data for use by createNewField
        currentFieldData = data.current_field;
        console.log('💾 Stored current field data:', currentFieldData);
        
        // Update progress and check for completion
        if (data.progress) {
            updateProgressBar(data.progress.total, data.progress.processed);
            
            // Additional check: if processed equals total, we're done
            if (data.progress.processed >= data.progress.total && data.progress.total > 0) {
                console.log('🎯 Detected completion based on progress numbers:', data.progress.processed, '>=', data.progress.total);
                updateProgressBar(data.progress.total, data.progress.total);
                showElement('sessionCompleted');
                hideElement('currentFieldSection');
                return;
            }
        }
        
        // Update batch size from server response
        if (data.batch_info && data.batch_info.batch_size) {
            batchSize = data.batch_info.batch_size;
        }
        
        // Display current field
        displayCurrentField(data.current_field);
        
        // Check if we need bulk processing for this field
        if (data.batch_info && data.batch_info.need_bulk_processing) {
            console.log('🚀 Need bulk processing for current batch');
            // Trigger batch processing
            setTimeout(() => {
                processBulkFields();
            }, 500); // Small delay to let current field display
            return;
        }
        
        // Display matches if they exist and are processed
        if (data.current_field.matches && data.current_field.matches.length > 0 && data.current_field.processed) {
            console.log('📋 Displaying matches from field response:', data.current_field.matches);
            currentMatches = data.current_field.matches;
            displayMatches(data.current_field.matches);
            showElement('matchesSection');
        } else if (data.current_field.processed) {
            console.log('❌ No matches found for this field');
            showElement('matchesSection');
            const matchesList = document.getElementById('matchesList');
            matchesList.innerHTML = '<p>No good matches found for this field.</p>';
        } else {
            console.log('⏳ Field not yet processed, waiting for bulk processing');
        }
        
        // Store new field suggestion if it exists
        if (data.current_field.new_field_suggestion) {
            currentNewFieldSuggestion = data.current_field.new_field_suggestion;
        }
        
        // Hide loading, show field card
        hideElement('loadingNextField');
        showElement('currentFieldSection');
        
    } catch (error) {
        console.error('❌ Error loading next field:', error);
        showAlert('uploadStatus', 'Failed to load next field: ' + error.message, 'error');
        hideElement('loadingNextField');
    }
}

async function improveMatches() {
    const feedbackText = document.getElementById('bulkMatchFeedback').value.trim();
    
    if (!feedbackText) {
        showAlert('uploadStatus', 'Please provide feedback to improve matches', 'error');
        return;
    }
    
    showLoading('improveBulkMatchesIcon', true);
    disableAllInteraction(); // Prevent user interactions during processing
    
    // Use stored current field data instead of calling getCurrentFieldData()
    if (!currentFieldData) {
        console.log('No current field data available for improve matches');
        showAlert('uploadStatus', 'No current field data available. Please try again.', 'error');
        showLoading('improveBulkMatchesIcon', false);
        enableAllInteraction(); // Re-enable interactions before returning
        return;
    }
    
    try {
        const response = await fetch('/cdd-agent/web/check-field', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({
                field_name: currentFieldData.field_name,
                field_definition: currentFieldData.field_definition,
                action_type: 'improve_matches',
                feedback_text: feedbackText
            })
        });
        
        await handleApiResponse(response, 'Improve matches');
        const result = await response.json();
        
        if (response.ok) {
            currentMatches = result.matches || [];
            
            if (result.status === 'matched' && currentMatches.length > 0) {
                // Display improved matches
                console.log('Displaying improved matches:', currentMatches);
                displayMatches(currentMatches);
                showElement('matchesSection');
                hideElement('newFieldSection');
            } else {
                // Still no good matches
                const matchesList = document.getElementById('matchesList');
                if (matchesList) {
                    matchesList.innerHTML = '<p style="text-align: center; color: #666; font-style: italic;">No good matches found even with feedback.</p>';
                }
            }
            
            // Clear feedback after applying
            document.getElementById('bulkMatchFeedback').value = '';
        } else {
            console.error('Error improving matches:', result);
            showAlert('uploadStatus', result.detail || 'Error improving matches', 'error');
        }
    } catch (error) {
        console.error('Error in improveMatches:', error);
        showAlert('uploadStatus', 'Unable to improve matches. Please try again.', 'error');
    } finally {
        showLoading('improveBulkMatchesIcon', false);
        enableAllInteraction(); // Re-enable user interactions
    }
}

async function createNewField() {
    console.log('=== createNewField called ===');
    
    showLoading('newFieldLoadingIcon', true);
    disableAllInteraction(); // Prevent user interactions during processing
    
    try {
        // Use stored current field data instead of calling getCurrentFieldData()
        if (!currentFieldData) {
            console.log('No current field data available');
            showAlert('uploadStatus', 'No current field data available. Please try again.', 'error');
            showLoading('newFieldLoadingIcon', false);
            enableAllInteraction(); // Re-enable interactions before returning
            return;
        }
        
        console.log('Creating new field suggestion for:', currentFieldData.field_name);
        
        const requestBody = {
            field_name: currentFieldData.field_name,
            field_definition: currentFieldData.field_definition,
            action_type: 'create_new_field'
        };
        console.log('📤 SENDING REQUEST:', JSON.stringify(requestBody, null, 2));
        
        const response = await fetch('/cdd-agent/web/check-field', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify(requestBody)
        });
        
        await handleApiResponse(response, 'Create new field');
        const result = await response.json();
        console.log('📥 RECEIVED RESPONSE:', result);
        
        if (response.ok && result.new_field_suggestion) {
            console.log('SUCCESS: Created new field suggestion:', result.new_field_suggestion);
            currentNewFieldSuggestion = result.new_field_suggestion;
            displayNewFieldSuggestion(result.new_field_suggestion);
            hideElement('matchesSection');
            showElement('newFieldSection');
            console.log('New field suggestion displayed successfully');
        } else {
            console.error('ERROR: Failed to create new field:', result);
            showAlert('uploadStatus', result.detail || 'Failed to create new field suggestion', 'error');
        }
    } catch (error) {
        console.error('EXCEPTION in createNewField:', error);
        showAlert('uploadStatus', 'Unable to create new field. Please try again.', 'error');
    } finally {
        showLoading('newFieldLoadingIcon', false);
        enableAllInteraction(); // Re-enable user interactions
    }
}

async function improveNewField() {
    const feedbackText = document.getElementById('bulkNewFieldFeedback').value.trim();
    
    if (!feedbackText) {
        showAlert('uploadStatus', 'Please provide feedback to improve the new field', 'error');
        return;
    }
    
    showLoading('improveBulkNewFieldIcon', true);
    disableAllInteraction(); // Prevent user interactions during processing
    
    // Use stored current field data instead of calling getCurrentFieldData()
    if (!currentFieldData) {
        console.log('No current field data available for improve new field');
        showAlert('uploadStatus', 'No current field data available. Please try again.', 'error');
        showLoading('improveBulkNewFieldIcon', false);
        enableAllInteraction(); // Re-enable interactions before returning
        return;
    }
    
    try {
        const response = await fetch('/cdd-agent/web/check-field', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({
                field_name: currentFieldData.field_name,
                field_definition: currentFieldData.field_definition,
                action_type: 'create_new_field',
                feedback_text: feedbackText
            })
        });
        
        await handleApiResponse(response, 'Improve new field');
        const result = await response.json();
        
        if (result.new_field_suggestion) {
            console.log('Improved new field suggestion:', result.new_field_suggestion);
            currentNewFieldSuggestion = result.new_field_suggestion;
            displayNewFieldSuggestion(result.new_field_suggestion);
            // Clear feedback after applying
            document.getElementById('bulkNewFieldFeedback').value = '';
            showAlert('uploadStatus', 'New field suggestion updated with your feedback!', 'success');
        } else {
            console.error('Error improving new field:', result);
            showAlert('uploadStatus', 'Failed to improve new field', 'error');
        }
    } catch (error) {
        console.error('Error in improveNewField:', error);
        showAlert('uploadStatus', 'Unable to improve new field. Please try again.', 'error');
    } finally {
        showLoading('improveBulkNewFieldIcon', false);
        enableAllInteraction(); // Re-enable user interactions
    }
}

function updateProgressBar(total, processed) {
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    
    const percentage = total > 0 ? (processed / total) * 100 : 0;
    progressFill.style.width = `${percentage}%`;
    progressText.textContent = `${processed} / ${total} fields processed`;
}

function displayCurrentField(fieldData) {
    const fieldInfo = document.getElementById('currentFieldInfo');
    fieldInfo.innerHTML = `
        <h4>Field Name: ${fieldData.field_name}</h4>
        <p><strong>Definition:</strong> ${fieldData.field_definition}</p>
    `;
}

function displayMatches(matches) {
    const matchesList = document.getElementById('matchesList');
    matchesList.innerHTML = '';
    
    matches.forEach((match, index) => {
        const confidenceClass = match.confidence_score >= 0.8 ? 'confidence-high' : 
                               match.confidence_score >= 0.6 ? 'confidence-medium' : 'confidence-low';
        
        const matchElement = document.createElement('div');
        matchElement.className = 'match-item';
        matchElement.onclick = () => selectMatch(index);
        
        matchElement.innerHTML = `
            <div class="match-header">
                <span class="match-attribute">${match.cdd_field}</span>
                <span class="confidence-badge ${confidenceClass}">${Math.round(match.confidence_score * 100)}%</span>
            </div>
            <div class="match-details">
                <p><strong>Category:</strong> ${match.category}</p>
                <p><strong>Description:</strong> ${match.description}</p>
                <p><strong>Display Name:</strong> ${match.display_name || 'N/A'}</p>
                <p><strong>Data Type:</strong> ${match.data_type || 'N/A'}</p>
            </div>
        `;
        
        matchesList.appendChild(matchElement);
    });
}

async function acceptMatch(index) {
    console.log('=== acceptMatch called with index:', index);
    console.trace('acceptMatch call stack');
    
    // Prevent rapid processing - but only if we're already processing
    if (isProcessingField) {
        console.log('Skipping acceptMatch - already processing field');
        return;
    }
    
    // Prevent rapid successive clicks (reduce from 2000ms to 500ms for better UX)
    const now = Date.now();
    if ((now - lastProcessTime) < 500) {
        console.log('Skipping acceptMatch - too soon since last process');
        return;
    }
    
    if (index < 0 || index >= currentMatches.length) {
        showAlert('uploadStatus', 'Invalid match selection.', 'error');
        return;
    }
    
    isProcessingField = true;
    lastProcessTime = now;
    
    disableAllInteraction();
    showElement('loadingNextField');
    
    try {
        const selectedMatch = currentMatches[index];
        const formData = new FormData();
        formData.append('action', 'match');
        formData.append('selected_match', selectedMatch.cdd_field); // Send the actual attribute name
        
        console.log('Sending accept match request to server with:', selectedMatch.cdd_field);
        
        const response = await fetch(`/cdd-agent/web/session/${currentSessionId}/process-field`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            },
            body: formData
        });
        
        await handleApiResponse(response, 'Accept match');
        const result = await response.json();
        
        console.log('Accept match successful, moving to next field');
        // Clear current matches for next field
        currentMatches = [];
        
        // Hide matches section
        hideElement('matchesSection');
        
        // Update progress if available in response
        if (result.progress) {
            updateProgressBar(result.progress.total || 0, result.progress.processed || 0);
        }
        
        // Move to next field
        await loadNextField();
    } catch (error) {
        console.error('Error accepting match:', error);
        showAlert('uploadStatus', 'Unable to accept match. Please check your connection.', 'error');
        hideElement('loadingNextField');
    }
    
    isProcessingField = false;
    enableAllInteraction();
}

function displayNewFieldSuggestion(suggestion) {
    const newFieldDisplay = document.getElementById('newFieldDisplay');
    newFieldDisplay.innerHTML = `
        <div class="new-field-item">
            <strong>Category:</strong> <span>${suggestion.category || 'N/A'}</span>
        </div>
        <div class="new-field-item">
            <strong>Attribute Name:</strong> <span>${suggestion.attribute || 'N/A'}</span>
        </div>
        <div class="new-field-item">
            <strong>Description:</strong> <span>${suggestion.description || 'N/A'}</span>
        </div>
        <div class="new-field-item">
            <strong>Display Label:</strong> <span>${suggestion.label || 'N/A'}</span>
        </div>
        <div class="new-field-item">
            <strong>Data Type:</strong> <span>${suggestion.data_type || 'STRING'}</span>
        </div>
        <div class="new-field-item">
            <strong>Tag:</strong> <span>${suggestion.tag || 'N/A'}</span>
        </div>
    `;
}

// File downloads
async function downloadFiles() {
    try {
        const response = await fetch(`/cdd-agent/web/session/${currentSessionId}/download`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        await handleApiResponse(response, 'Download files');
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // Create filename with original name and local timestamp
        let filename = 'updated_mapping_file.xlsx';
        if (selectedFile && selectedFile.name) {
            // Get original filename without extension
            const originalName = selectedFile.name.replace(/\.[^/.]+$/, '');
            // Create local timestamp
            const now = new Date();
            const timestamp = now.getFullYear() + 
                String(now.getMonth() + 1).padStart(2, '0') + 
                String(now.getDate()).padStart(2, '0') + '_' +
                String(now.getHours()).padStart(2, '0') + 
                String(now.getMinutes()).padStart(2, '0') + 
                String(now.getSeconds()).padStart(2, '0');
            filename = `${originalName}_${timestamp}.xlsx`;
        }
        
        a.download = filename;
        
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showAlert('uploadStatus', `Updated mapping file downloaded: ${filename}`, 'success');
        
    } catch (error) {
        console.error('Download error:', error);
        showAlert('uploadStatus', 'Unable to download file. Please check your connection.', 'error');
    }
}

async function clearSession() {
    if (!currentSessionId) {
        console.log('No active session to clear');
        return;
    }
    
    try {
        const response = await fetch(`/cdd-agent/web/session/${currentSessionId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        await handleApiResponse(response, 'Clear session');
        const data = await response.json();
        console.log('Session cleared:', data);
        
        // Reset all state
        currentSessionId = null;
        currentMatches = [];
        currentNewFieldSuggestion = null;
        currentFieldData = null;
        feedbackHistory = [];
        batchSize = 5;
        
        showAlert('uploadStatus', 'Session cleared successfully. You can now start a new session.', 'success');
        
    } catch (error) {
        console.error('Error clearing session:', error);
        // Still reset local state even if server call fails
        currentSessionId = null;
        currentMatches = [];
        currentNewFieldSuggestion = null;
        currentFieldData = null;
        feedbackHistory = [];
        batchSize = 5;
        
        showAlert('uploadStatus', 'Session cleared locally. You can start a new session.', 'info');
    }
}

function exitProcessing() {
    if (confirm('Are you sure you want to exit? This will clear your current session and you will lose any unsaved progress.')) {
        // Clear the session on the server
        clearSession().then(() => {
            // Hide the entire processing interface (this contains the progress bar)
            hideElement('processingInterface');
            
            // Reset UI state
            hideElement('currentFieldSection');
            hideElement('sessionCompleted');
            hideElement('loadingNextField');
            hideElement('matchesSection');
            hideElement('newFieldSection');
            showElement('fileUploadSection');
            
            // Reset progress bar
            updateProgressBar(0, 0);
            
            // Reset file input
            const fileInput = document.getElementById('fileInput');
            if (fileInput) {
                fileInput.value = '';
            }
            selectedFile = null;
            
            // Clear any existing alerts
            hideElement('uploadStatus');
            
            // Clear feedback inputs
            const bulkMatchFeedback = document.getElementById('bulkMatchFeedback');
            const bulkNewFieldFeedback = document.getElementById('bulkNewFieldFeedback');
            if (bulkMatchFeedback) bulkMatchFeedback.value = '';
            if (bulkNewFieldFeedback) bulkNewFieldFeedback.value = '';
            
            console.log('✅ Processing session ended and cleaned up');
        });
    }
}

// Single Field Check Functions (Updated for new workflow)
async function checkSingleField() {
    const fieldName = document.getElementById('fieldName').value.trim();
    const fieldDefinition = document.getElementById('fieldDefinition').value.trim();
    
    if (!fieldName || !fieldDefinition) {
        showAlert('singleFieldStatus', 'Please enter both field name and definition', 'error');
        return;
    }
    
    showLoading('singleCheckLoadingIcon', true);
    hideElement('singleFieldResults');
    hideElement('singleFieldMatches');
    hideElement('singleFieldNewField');
    
    try {
        console.log('Making API call to check field:', fieldName);
        
        const response = await fetch('/cdd-agent/web/check-field', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({
                field_name: fieldName,
                field_definition: fieldDefinition,
                action_type: 'find_matches'
            })
        });
        
        console.log('API response status:', response.status);
        console.log('API response headers:', response.headers);
        
        await handleApiResponse(response, 'Check single field');
        const result = await response.json();
        console.log('API response data:', result);
        
        showAlert('singleFieldStatus', 'Field check completed successfully!', 'success');
        displaySingleFieldResults(result);
    } catch (error) {
        console.error('Single field check error details:', error);
        console.error('Error type:', error.constructor.name);
        console.error('Error message:', error.message);
        console.error('Error stack:', error.stack);
        
        let errorMessage = 'Unable to connect to server. Please check your connection.';
        
        // More specific error messages based on error type
        if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
            errorMessage = 'Network error: Unable to reach the server. Please check your connection and try again.';
        } else if (error instanceof SyntaxError && error.message.includes('JSON')) {
            errorMessage = 'Server response error: Invalid JSON format. Please try again.';
        } else if (error.message) {
            errorMessage = `Error: ${error.message}`;
        }
        
        showAlert('singleFieldStatus', errorMessage, 'error');
    }
    
    showLoading('singleCheckLoadingIcon', false);
}

function displaySingleFieldResults(result) {
    console.log('Displaying single field results:', result);
    
    try {
        showElement('singleFieldResults');
        
        if (result.status === 'matched' && result.matches && result.matches.length > 0) {
            // Display matches
            console.log('Displaying matches:', result.matches);
            displaySingleFieldMatches(result.matches);
            showElement('singleFieldMatches');
            hideElement('singleFieldNewField');
        } else if (result.status === 'new_suggestion' && result.new_field_suggestion) {
            // Display new field suggestion
            console.log('Displaying new field suggestion:', result.new_field_suggestion);
            displaySingleFieldNewField(result.new_field_suggestion);
            hideElement('singleFieldMatches');
            showElement('singleFieldNewField');
            showAlert('singleFieldStatus', 'New field suggestion created!', 'success');
        } else {
            // No good matches and no new field suggestion - auto-trigger new field creation
            console.log('No matches or suggestions found, status:', result.status);
            hideElement('singleFieldMatches');
            hideElement('singleFieldNewField');
            
            // Show message and auto-trigger new field creation
            showAlert('singleFieldStatus', 'No good matches found. Automatically creating new field suggestion...', 'info');
            
            // Auto-trigger new field creation
            setTimeout(() => {
                createSingleFieldNewField();
            }, 1000); // Small delay to let user see the message
        }
    } catch (error) {
        console.error('Error displaying results:', error);
        showAlert('singleFieldStatus', `Error displaying results: ${error.message}`, 'error');
    }
}

function displaySingleFieldMatches(matches) {
    const matchesList = document.getElementById('singleFieldMatchesList');
    matchesList.innerHTML = '';
    
    matches.forEach((match, index) => {
        const matchDiv = document.createElement('div');
        matchDiv.className = 'match-item';
        matchDiv.innerHTML = `
            <div class="match-header">
                <span class="match-name">${match.cdd_field}</span>
                <span class="confidence-badge confidence-${getConfidenceLevel(match.confidence_score)}">
                    ${Math.round(match.confidence_score * 100)}%
                </span>
            </div>
            <div class="match-details">
                ${match.display_name ? `<strong>Display Name:</strong> ${match.display_name}<br>` : ''}
                ${match.data_type ? `<strong>Data Type:</strong> ${match.data_type}<br>` : ''}
                ${match.category ? `<strong>Category:</strong> ${match.category}<br>` : ''}
                ${match.description ? `<strong>Description:</strong> ${match.description}<br>` : ''}
            </div>
        `;
        matchesList.appendChild(matchDiv);
    });
}

function getConfidenceLevel(score) {
    if (score >= 0.8) return 'high';
    if (score >= 0.6) return 'medium';
    return 'low';
}

async function improveSingleFieldMatches() {
    const fieldName = document.getElementById('fieldName').value.trim();
    const fieldDefinition = document.getElementById('fieldDefinition').value.trim();
    const feedback = document.getElementById('matchFeedback').value.trim();
    
    if (!feedback) {
        showAlert('singleFieldStatus', 'Please provide feedback to improve matches', 'error');
        return;
    }
    
    showLoading('improveSingleFieldMatchesIcon', true);
    
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
                action_type: 'improve_matches',
                feedback_text: feedback
            })
        });
        
        await handleApiResponse(response, 'Improve single field matches');
        const result = await response.json();
        
        showAlert('singleFieldStatus', 'Matches improved with your feedback!', 'success');
        displaySingleFieldMatches(result.matches);
        // Clear feedback after applying
        document.getElementById('matchFeedback').value = '';
    } catch (error) {
        console.error('Improve matches error:', error);
        showAlert('singleFieldStatus', 'Unable to improve matches. Please try again.', 'error');
    }
    
    showLoading('improveSingleFieldMatchesIcon', false);
}

async function createSingleFieldNewField() {
    const fieldName = document.getElementById('fieldName').value.trim();
    const fieldDefinition = document.getElementById('fieldDefinition').value.trim();
    
    showLoading('createSingleFieldNewFieldIcon', true);
    
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
                action_type: 'create_new_field'
            })
        });
        
        await handleApiResponse(response, 'Create single field new field');
        const result = await response.json();
        
        if (result.new_field_suggestion) {
            showAlert('singleFieldStatus', 'New field suggestion created!', 'success');
            displaySingleFieldNewField(result.new_field_suggestion);
            hideElement('singleFieldMatches');
            showElement('singleFieldNewField');
        } else {
            showAlert('singleFieldStatus', 'Failed to create new field suggestion', 'error');
        }
    } catch (error) {
        console.error('Create new field error:', error);
        showAlert('singleFieldStatus', 'Unable to create new field. Please try again.', 'error');
    }
    
    showLoading('createSingleFieldNewFieldIcon', false);
}

function displaySingleFieldNewField(suggestion) {
    const display = document.getElementById('singleFieldNewFieldDisplay');
    display.innerHTML = `
        <div class="new-field-item">
            <strong>Category:</strong> <span>${suggestion.category}</span>
        </div>
        <div class="new-field-item">
            <strong>Attribute Name:</strong> <span>${suggestion.attribute}</span>
        </div>
        <div class="new-field-item">
            <strong>Description:</strong> <span>${suggestion.description}</span>
        </div>
        <div class="new-field-item">
            <strong>Display Label:</strong> <span>${suggestion.label}</span>
        </div>
        <div class="new-field-item">
            <strong>Data Type:</strong> <span>${suggestion.data_type || 'STRING'}</span>
        </div>
        <div class="new-field-item">
            <strong>Tag:</strong> <span>${suggestion.tag}</span>
        </div>
    `;
}

async function improveSingleFieldNewField() {
    const fieldName = document.getElementById('fieldName').value.trim();
    const fieldDefinition = document.getElementById('fieldDefinition').value.trim();
    const feedback = document.getElementById('newFieldFeedback').value.trim();
    
    if (!feedback) {
        showAlert('singleFieldStatus', 'Please provide feedback to improve the new field', 'error');
        return;
    }
    
    showLoading('improveSingleFieldNewFieldIcon', true);
    
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
                action_type: 'create_new_field',
                feedback_text: feedback
            })
        });
        
        await handleApiResponse(response, 'Improve single field new field');
        const result = await response.json();
        
        if (result.new_field_suggestion) {
            showAlert('singleFieldStatus', 'New field improved with your feedback!', 'success');
            displaySingleFieldNewField(result.new_field_suggestion);
            // Clear feedback after applying
            document.getElementById('newFieldFeedback').value = '';
        } else {
            showAlert('singleFieldStatus', 'Failed to improve new field', 'error');
        }
    } catch (error) {
        console.error('Improve new field error:', error);
        showAlert('singleFieldStatus', 'Unable to improve new field. Please try again.', 'error');
    }
    
    showLoading('improveSingleFieldNewFieldIcon', false);
}

async function downloadSingleFieldNewField() {
    const fieldName = document.getElementById('fieldName').value.trim();
    const fieldDefinition = document.getElementById('fieldDefinition').value.trim();
    
    // Get current new field suggestion from display
    const display = document.getElementById('singleFieldNewFieldDisplay');
    if (!display.innerHTML.trim()) {
        showAlert('singleFieldStatus', 'No new field suggestion to download', 'error');
        return;
    }
    
    // Extract the new field data from the display
    const newFieldData = {};
    const items = display.querySelectorAll('.new-field-item');
    items.forEach(item => {
        const label = item.querySelector('strong').textContent.replace(':', '');
        const value = item.querySelector('span').textContent;
        
        switch (label) {
            case 'Category':
                newFieldData.category = value;
                break;
            case 'Attribute Name':
                newFieldData.attribute = value;
                break;
            case 'Description':
                newFieldData.description = value;
                break;
            case 'Display Label':
                newFieldData.label = value;
                break;
            case 'Data Type':
                newFieldData.data_type = value;
                break;
            case 'Tag':
                newFieldData.tag = value;
                break;
        }
    });
    
    try {
        const formData = new FormData();
        formData.append('field_name', fieldName);
        formData.append('field_definition', fieldDefinition);
        formData.append('new_field_json', JSON.stringify(newFieldData));
        
        const response = await fetch('/cdd-agent/web/download-single-field-suggestion', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            },
            body: formData
        });
        
        await handleApiResponse(response, 'Download single field new field');
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `new_field_suggestion_${fieldName.replace(/\s+/g, '_')}.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        showAlert('singleFieldStatus', 'New field suggestion downloaded as Excel!', 'success');
    } catch (error) {
        console.error('Download error:', error);
        showAlert('singleFieldStatus', 'Unable to download new field suggestion. Please try again.', 'error');
    }
}

async function downloadExampleFile() {
    try {
        const response = await fetch('/cdd-agent/web/example-file', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        await handleApiResponse(response, 'Download example file');
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // Try to get filename from Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'example_cdd_mapping.xlsx';
        
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (filenameMatch && filenameMatch[1]) {
                filename = filenameMatch[1].replace(/['"]/g, '');
            }
        }
        
        // Ensure filename has .xlsx extension
        if (!filename.toLowerCase().endsWith('.xlsx')) {
            filename = filename.replace(/\.[^/.]+$/, '') + '.xlsx';
        }
        
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showAlert('singleFieldStatus', 'Example file downloaded successfully!', 'success');
        
    } catch (error) {
        console.error('Download error:', error);
        showAlert('singleFieldStatus', 'Unable to download file. Please check your connection and try again.', 'error');
    }
}

// Export single field result
function exportSingleFieldResult(format) {
    if (!currentSingleFieldResult) {
        showAlert('singleFieldStatus', 'No field result to export.', 'error');
        return;
    }

    const fieldName = document.getElementById('fieldName').value.trim();
    const fieldDefinition = document.getElementById('fieldDefinition').value.trim();

    // Create export data structure
    const exportData = {
        field_name: fieldName,
        field_definition: fieldDefinition,
        status: currentSingleFieldResult.status,
        confidence_threshold: currentSingleFieldResult.confidence_threshold,
        matches: currentSingleFieldResult.matches || [],
        new_field_suggestion: currentSingleFieldResult.new_field_suggestion || null
    };

    let content, mediaType, filename;

    if (format === 'csv') {
        // Create CSV content
        let csvContent = 'Field Name,Field Definition,Status,Confidence Threshold\n';
        csvContent += `"${fieldName}","${fieldDefinition}","${currentSingleFieldResult.status}","${currentSingleFieldResult.confidence_threshold}"\n\n`;

        if (exportData.matches.length > 0) {
            csvContent += 'MATCHES\n';
            csvContent += 'CDD Field,Category,Data Type,Confidence Score,Description\n';
            exportData.matches.forEach(match => {
                csvContent += `"${match.cdd_field}","${match.category || ''}","${match.data_type || ''}","${match.confidence_score}","${(match.description || '').replace(/"/g, '""')}"\n`;
            });
            csvContent += '\n';
        }

        if (exportData.new_field_suggestion) {
            const suggestion = exportData.new_field_suggestion;
            csvContent += 'NEW FIELD SUGGESTION\n';
            csvContent += 'Category,Attribute,Description,Label,Data Type\n';
            csvContent += `"${suggestion.category}","${suggestion.attribute}","${(suggestion.description || '').replace(/"/g, '""')}","${suggestion.label}","${suggestion.data_type || 'STRING'}"\n`;
        }

        content = csvContent;
        mediaType = 'text/csv';
        filename = `field_check_${fieldName}_${Date.now()}.csv`;
    } else {
        // Create JSON content
        content = JSON.stringify(exportData, null, 2);
        mediaType = 'application/json';
        filename = `field_check_${fieldName}_${Date.now()}.json`;
    }

    // Create and trigger download
    const blob = new Blob([content], { type: mediaType });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);

    showAlert('singleFieldStatus', `Results exported as ${format.toUpperCase()}: ${filename}`, 'success');
}

// Helper function to get current field data - REMOVED (now using stored currentFieldData)
// async function getCurrentFieldData() { ... }

async function acceptNewField() {
    console.log('✅ acceptNewField called');
    
    if (!currentNewFieldSuggestion) {
        showAlert('uploadStatus', 'No new field suggestion to accept.', 'error');
        return;
    }
    
    // Prevent rapid processing
    const now = Date.now();
    if (isProcessingField || (now - lastProcessTime) < 2000) {
        console.log('Skipping acceptNewField - too soon or already processing');
        return;
    }
    
    isProcessingField = true;
    lastProcessTime = now;
    
    disableAllInteraction();
    showElement('loadingNextField');
    
    try {
        const formData = new FormData();
        formData.append('action', 'new_field');
        formData.append('new_field_json', JSON.stringify(currentNewFieldSuggestion));
        
        console.log('Sending accept new field request to server');
        
        const response = await fetch(`/cdd-agent/web/session/${currentSessionId}/process-field`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            },
            body: formData
        });
        
        await handleApiResponse(response, 'Accept new field');
        const result = await response.json();
        
        console.log('Accept new field successful, moving to next field');
        // Clear current suggestion for next field
        currentNewFieldSuggestion = null;
        
        // Hide new field section
        hideElement('newFieldSection');
        
        // Update progress if available in response
        if (result.progress) {
            updateProgressBar(result.progress.total || 0, result.progress.processed || 0);
        }
        
        // Move to next field
        await loadNextField();
    } catch (error) {
        console.error('Error accepting new field:', error);
        showAlert('uploadStatus', 'Unable to accept new field. Please check your connection.', 'error');
        hideElement('loadingNextField');
    }
    
    isProcessingField = false;
    enableAllInteraction();
}

async function skipField() {
    console.log('⏭️ skipField called');
    
    // Prevent rapid processing
    const now = Date.now();
    if (isProcessingField || (now - lastProcessTime) < 2000) {
        console.log('Skipping skipField - too soon or already processing');
        return;
    }
    
    isProcessingField = true;
    lastProcessTime = now;
    
    disableAllInteraction();
    showElement('loadingNextField');
    
    try {
        const formData = new FormData();
        formData.append('action', 'skip');
        
        console.log('Sending skip request to server');
        
        const response = await fetch(`/cdd-agent/web/session/${currentSessionId}/process-field`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            },
            body: formData
        });
        
        await handleApiResponse(response, 'Skip field');
        const result = await response.json();
        
        console.log('Skip successful, moving to next field');
        // Clear current suggestion for next field
        currentNewFieldSuggestion = null;
        
        // Hide both sections
        hideElement('matchesSection');
        hideElement('newFieldSection');
        
        // Update progress if available in response
        if (result.progress) {
            updateProgressBar(result.progress.total || 0, result.progress.processed || 0);
        }
        
        // Move to next field
        await loadNextField();
    } catch (error) {
        console.error('Error skipping field:', error);
        showAlert('uploadStatus', 'Unable to skip field. Please check your connection.', 'error');
        hideElement('loadingNextField');
    }
    
    isProcessingField = false;
    enableAllInteraction();
}

// Clear authentication token
function clearToken() {
    authToken = null;
    localStorage.removeItem('cdd_auth_token');
    document.getElementById('authToken').value = '';
    document.getElementById('mainInterface').classList.add('hidden');
    showAlert('authStatus', 'Authentication token cleared', 'success');
} 