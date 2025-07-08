from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum

# Standard column headers for field mapping
class StandardFieldHeaders(str, Enum):
    FIELD_NAME = "field_name"
    CONTEXT_DEFINITION = "context_definition"
    CDD_CONFIRMED = "cdd_confirmed"
    CDD_BEST_GUESS = "cdd_best_guess"

# Request/Response Models
class FieldMappingRequest(BaseModel):
    field_name: str = Field(..., description="The field name to map")
    context_definition: str = Field(..., description="Context or definition of the field")
    cdd_field: Optional[str] = Field(None, description="Existing CDD field if already mapped")

class CDDMatchResult(BaseModel):
    cdd_field: str = Field(..., description="CDD field name")
    display_name: Optional[str] = Field(None, description="Display name of the CDD field")
    data_type: Optional[str] = Field(None, description="Data type of the CDD field")
    description: Optional[str] = Field(None, description="Description of the CDD field")
    category: Optional[str] = Field(None, description="Category the CDD field belongs to")
    confidence_score: float = Field(..., description="Confidence score for the match")

class NewCDDFieldSuggestion(BaseModel):
    category: str = Field(..., description="Technical Category Name")
    attribute: str = Field(..., description="New attribute name")
    description: str = Field(..., description="Description of the new field")
    label: str = Field(..., description="UI Label/name")
    tag: str = Field(default="ZM", description="Product tag")
    action: str = Field(default="New", description="Action type (New/Update/Deprecate)")
    partition_key_order: Optional[int] = Field(None, description="Partition Key Order")
    index_key: Optional[str] = Field(None, description="Index Key")
    data_type: Optional[str] = Field(None, description="Suggested data type")

class FieldMappingResponse(BaseModel):
    field_name: str
    context_definition: str
    matches: List[CDDMatchResult] = Field(default_factory=list)
    new_field_suggestion: Optional[NewCDDFieldSuggestion] = Field(None)
    status: str = Field(..., description="Status of the mapping (matched/new_suggestion/no_match)")

class BulkFieldMappingRequest(BaseModel):
    fields: List[FieldMappingRequest] = Field(..., description="List of fields to map")
    format: str = Field(default="json", description="Input format (json/csv)")

class BulkFieldMappingResponse(BaseModel):
    results: List[FieldMappingResponse]
    summary: Dict[str, int] = Field(..., description="Summary statistics")

class DatabasePopulationRequest(BaseModel):
    attributes_data: List[Dict[str, Any]] = Field(..., description="CDD attributes data")
    categories_data: List[Dict[str, Any]] = Field(..., description="CDD categories data")
    category_attributes_data: List[Dict[str, Any]] = Field(..., description="CDD category attributes mapping data")

class DatabasePopulationResponse(BaseModel):
    status: str = Field(..., description="Status of the population")
    attributes_count: int = Field(..., description="Number of attributes populated")
    categories_count: int = Field(..., description="Number of categories populated")
    category_attributes_count: int = Field(..., description="Number of category attribute mappings populated")
    message: str = Field(..., description="Status message")

# Internal Models
class EnrichedCDDAttribute(BaseModel):
    name: str
    display_name: Optional[str] = None
    data_type: Optional[str] = None
    description: Optional[str] = None
    tenant: Optional[str] = None
    enum_type: Optional[str] = None
    category: Optional[str] = None
    category_description: Optional[str] = None
    is_internal: Optional[bool] = None
    input_partition_order: Optional[int] = None
    output_partition_order: Optional[int] = None
    order: Optional[Union[int, float]] = None  # Allow both int and float from database
    products: Optional[List[str]] = None
    ma_internal: Optional[bool] = None

class CDDCategory(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    tenant: Optional[str] = None

class CDDCategoryAttribute(BaseModel):
    category_name: str
    attribute_name: str
    is_internal: Optional[bool] = None
    input_partition_order: Optional[int] = None
    output_partition_order: Optional[int] = None
    order: Optional[int] = None
    products: Optional[List[str]] = None
    tenant: Optional[str] = None
    ma_internal: Optional[bool] = None

# Additional models for authentication (from user's examples)
class TokenData(BaseModel):
    token: str
    payload: dict

class Entitlement(BaseModel):
    name: str
    startDate: datetime
    endDate: datetime

class PermissionsData(BaseModel):
    entitlements: List[Entitlement]
    roles: List[str]

class ResultOut(BaseModel):
    result: Any

class TaskRequest(BaseModel):
    task: str = Field(..., max_length=1000)
    return_json: Optional[bool] = False
    return_dataframe: Optional[bool] = False

class HealthResponse(BaseModel):
    status: str
    version: str 

# New models for front-end interface
class SingleFieldCheckRequest(BaseModel):
    field_name: str = Field(..., description="The field name to check")
    field_definition: str = Field(..., description="The field definition/description")
    force_new_suggestion: Optional[bool] = Field(False, description="Force generation of new field suggestion instead of matching")
    feedback_text: Optional[str] = Field(None, description="User feedback to improve matching or new field creation")
    action_type: Optional[str] = Field("find_matches", description="Action type: 'find_matches', 'create_new_field', 'improve_matches', 'improve_new_field'")

class SingleFieldCheckResponse(BaseModel):
    field_name: str
    field_definition: str
    matches: List[CDDMatchResult] = Field(default_factory=list)
    new_field_suggestion: Optional[NewCDDFieldSuggestion] = Field(None)
    status: str = Field(..., description="Status: 'matched', 'new_suggestion', or 'no_match'")
    confidence_threshold: float = Field(default=0.6, description="Confidence threshold used")
    feedback_applied: bool = Field(False, description="Whether feedback was applied in this response")

# New model for single field new field download
class SingleFieldNewFieldDownload(BaseModel):
    field_name: str = Field(..., description="The original field name")
    field_definition: str = Field(..., description="The original field definition")
    new_field_suggestion: NewCDDFieldSuggestion = Field(..., description="The new field suggestion")
    created_at: datetime = Field(default_factory=datetime.now, description="When the suggestion was created")

class FileProcessingSession(BaseModel):
    session_id: str = Field(..., description="Unique session identifier")
    original_filename: str = Field(..., description="Original uploaded filename")
    total_fields: int = Field(..., description="Total number of fields to process")
    processed_fields: int = Field(default=0, description="Number of fields processed")
    status: str = Field(default="active", description="Session status: active, paused, completed")
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

class FileUploadResponse(BaseModel):
    session_id: str = Field(..., description="Session ID for tracking progress")
    message: str = Field(..., description="Upload status message")
    total_fields: int = Field(..., description="Total fields detected in file")
    processable_fields: int = Field(..., description="Fields that can be processed")
    sample_fields: List[Dict[str, str]] = Field(..., description="Sample of fields for preview")

class ProcessFieldRequest(BaseModel):
    session_id: str = Field(..., description="Session ID")
    field_index: int = Field(..., description="Index of field to process")
    action: str = Field(..., description="Action: 'match', 'new_field', 'skip'")
    selected_match: Optional[str] = Field(None, description="Selected CDD field name if matching")
    new_field_data: Optional[NewCDDFieldSuggestion] = Field(None, description="New field data if creating")

class ProcessFieldResponse(BaseModel):
    session_id: str
    field_index: int
    field_name: str
    action_taken: str
    updated_value: Optional[str] = Field(None, description="Value set in cdd_best_guess column")
    progress: Dict[str, int] = Field(..., description="Progress tracking")
    next_field: Optional[Dict[str, Any]] = Field(None, description="Next field to process")

class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    progress: Dict[str, int]
    current_field: Optional[Dict[str, Any]] = Field(None)
    can_download: bool = Field(default=False)

class DownloadRequest(BaseModel):
    session_id: str
    format: str = Field(default="csv", description="Download format: csv or json")

class ExampleFileResponse(BaseModel):
    filename: str
    content_type: str
    headers: Dict[str, str]
    sample_data: List[Dict[str, str]]
    description: str

# Bulk Processing Models for Web Interface
class BulkFieldData(BaseModel):
    field_name: str = Field(..., description="The field name")
    field_definition: str = Field(..., description="The field definition/description")
    index: int = Field(..., description="Index in the original file")

class BulkFieldCheckRequest(BaseModel):
    fields: List[BulkFieldData] = Field(..., description="List of fields to process in bulk (3-5 fields)")
    session_id: str = Field(..., description="Session ID for tracking")
    feedback_text: Optional[str] = Field(None, description="User feedback to improve matching")

class BulkFieldResult(BaseModel):
    field_name: str
    field_definition: str
    index: int
    processable_index: int = Field(..., description="Position in the processable_indices array")
    matches: List[CDDMatchResult] = Field(default_factory=list)
    new_field_suggestion: Optional[NewCDDFieldSuggestion] = Field(None)
    status: str = Field(..., description="Status: 'matched', 'new_suggestion', or 'no_match'")
    confidence_threshold: float = Field(default=0.6)

class BulkFieldCheckResponse(BaseModel):
    session_id: str
    results: List[BulkFieldResult] = Field(..., description="Results for each field")
    total_processed: int = Field(..., description="Number of fields processed")
    feedback_applied: bool = Field(False, description="Whether feedback was applied")
    processing_time: float = Field(..., description="Processing time in seconds")

# Description Compression Models
class DescriptionCompressionRequest(BaseModel):
    compress_all: bool = Field(True, description="Compress all descriptions in database")
    batch_size: int = Field(10, description="Batch processing size")
    max_tokens: int = Field(40, description="Target token count per description")
    dry_run: bool = Field(False, description="Preview changes without saving")

class DescriptionCompressionResponse(BaseModel):
    status: str = Field(..., description="Status: success, partial, failed")
    total_processed: int = Field(..., description="Total attributes processed")
    compressed_count: int = Field(..., description="Successfully compressed descriptions")
    failed_count: int = Field(..., description="Failed compression attempts")
    skipped_count: int = Field(..., description="Descriptions already short enough")
    message: str = Field(..., description="Status message")
    preview_samples: Optional[List[Dict[str, str]]] = Field(None, description="Sample compressions for dry run")