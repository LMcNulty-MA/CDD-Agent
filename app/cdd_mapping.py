import pandas as pd
import json
import os
import sys
from typing import List, Dict, Optional, Tuple
import openai
import keyboard
import time
import random
import re

# ANSI color codes
RED = "\033[91m"
WHITE = "\033[37m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

# Add parent directory to sys.path to find config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configuration and database imports
from app.config import settings
from app.core.documentdb import MongoDBClient  # Using sync client for CLI
from app.core.models import StandardFieldHeaders
from app.core.utils import save_prompt_and_response

# Configuration
OPENAI_API_KEY = settings.OPENAI_API_KEY
MODEL = settings.MODEL_TO_USE
DOCDB_URI = settings.DOCDB_URI
DOCDB_DATABASE_NAME = settings.DOCDB_DATABASE_NAME
INPUT_FILE_PATH = settings.FIELD_NEED_MAPPING_FILE
OUTPUT_FILE_PATH = settings.NEW_CDD_FIELD_REQUEST_FILE

print(f"{WHITE}Loaded MODEL: {MODEL}{RESET}")
print(f"{WHITE}Database: {DOCDB_DATABASE_NAME}{RESET}")
print(f"{WHITE}Input File: {INPUT_FILE_PATH}{RESET}")
print(f"{WHITE}Output File: {OUTPUT_FILE_PATH}{RESET}")

# Determine file formats based on extensions
INPUT_FORMAT = "json" if INPUT_FILE_PATH.lower().endswith('.json') else "csv"
OUTPUT_FORMAT = "json" if OUTPUT_FILE_PATH.lower().endswith('.json') else "csv"

print(f"{WHITE}Input Format: {INPUT_FORMAT}, Output Format: {OUTPUT_FORMAT}{RESET}")
print(f"{WHITE}Prompt Saving: {'Enabled' if settings.SAVE_PROMPTS_TO_FILE else 'Disabled'}{RESET}")

# Set up OpenAI client
openai.api_key = OPENAI_API_KEY
client = openai.OpenAI()

# Initialize MongoDB client
db_client = MongoDBClient(DOCDB_URI, DOCDB_DATABASE_NAME)

def load_cdd_guidelines():
    """Load the comprehensive CDD guidelines from context file"""
    guidelines_path = os.path.join(os.path.dirname(__file__), "..", "context", "guidelines_for_adding_to_cdd.txt")
    try:
        with open(guidelines_path, 'r', encoding='utf-8') as f:
            guidelines = f.read()
        return guidelines
    except FileNotFoundError:
        print(f"{YELLOW}Guidelines file not found, using default guidelines{RESET}")
        return """
        CDD FIELD NAMING & FORMATTING GUIDELINES:
        - Use camelCase (e.g., entityIncorporationName, interestRateSpread)
        - Must be less than 64 characters
        - Use descriptive names reflecting content/purpose
        - Avoid acronyms unless widely used
        - For boolean fields: prefix with "is", "has"
        - For dates: include "Date" in name
        - For amounts: include "amount", "payment", "price"
        - For rates: include "rate" in name
        """

def load_input_file(file_path: str) -> pd.DataFrame:
    """Load input file (CSV or JSON) with standardized column mapping"""
    print(f"{WHITE}Loading input file: {file_path}{RESET}")
    
    if not os.path.exists(file_path):
        print(f"{RED}File not found: {file_path}{RESET}")
        sys.exit(1)
    
    if file_path.lower().endswith('.json'):
        # Load JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        df = pd.DataFrame(data)
    else:
        # Load CSV file with encoding detection
        encodings = ['utf-8', 'windows-1252', 'latin-1']
        df = None
        for encoding in encodings:
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if df is None:
            raise ValueError(f"Could not read file {file_path} with any supported encoding")
    
    # Standardize column names
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
    
    # Validate required columns exist
    required_cols = [StandardFieldHeaders.FIELD_NAME.value, StandardFieldHeaders.CONTEXT_DEFINITION.value]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        print(f"{RED}Error: Missing required columns: {missing_cols}{RESET}")
        print(f"{WHITE}Available columns: {list(df.columns)}{RESET}")
        print(f"{WHITE}Expected columns: field_name, context_definition, cdd_confirmed (optional), cdd_best_guess (optional){RESET}")
        sys.exit(1)
    
    # Add missing columns if not present and ensure proper data types
    if StandardFieldHeaders.CDD_CONFIRMED.value not in df.columns:
        df[StandardFieldHeaders.CDD_CONFIRMED.value] = ""
    if StandardFieldHeaders.CDD_BEST_GUESS.value not in df.columns:
        df[StandardFieldHeaders.CDD_BEST_GUESS.value] = ""
    
    # Convert string columns to object dtype to avoid pandas warnings
    df[StandardFieldHeaders.CDD_CONFIRMED.value] = df[StandardFieldHeaders.CDD_CONFIRMED.value].astype('object')
    df[StandardFieldHeaders.CDD_BEST_GUESS.value] = df[StandardFieldHeaders.CDD_BEST_GUESS.value].astype('object')
    
    print(f"{WHITE}Loaded {len(df)} fields with standardized columns{RESET}")
    print(f"{WHITE}Columns: {list(df.columns)}{RESET}")
    
    return df

def get_all_cdd_data_from_db() -> Tuple[List[Dict], List[Dict]]:
    """Get all CDD attributes and categories from MongoDB in one call"""
    try:
        # Get all attributes and categories (no limit)
        attributes = db_client.get_documents("attributes", {}, limit=0)
        categories = db_client.get_documents("categories", {}, limit=0)
        print(f"{WHITE}Loaded {len(attributes)} CDD attributes and {len(categories)} categories from database{RESET}")
        return attributes, categories
    except Exception as e:
        print(f"{RED}Error loading CDD data from database: {e}{RESET}")
        print(f"{WHITE}Make sure the database is populated. Use the populate-database API endpoint first.{RESET}")
        sys.exit(1)

def create_optimized_matching_context(attributes: List[Dict]) -> str:
    """Create optimized context for field matching with display names and data types"""
    context_parts = []
    context_parts.append("AVAILABLE CDD ATTRIBUTES:")
    for attr in attributes:
        name = attr.get('name', '')
        display_name = attr.get('displayName', '')  # Database uses camelCase
        data_type = attr.get('dataType', '')  # Database uses camelCase
        category = attr.get('category', '')
        description = attr.get('description', '')
        
        # Start with technical name
        context_line = f"• {name}"
        
        # Add display name if different from technical name
        if display_name and display_name != name:
            context_line += f" \"{display_name}\""
        
        # Add data type in brackets
        if data_type:
            context_line += f" [{data_type}]"
        
        # Add category in parentheses
        if category:
            context_line += f" ({category})"
        
        # Add description with colon
        if description:
            context_line += f": {description}"
        
        context_parts.append(context_line)
    return "\n".join(context_parts)

def create_rich_category_context(categories: List[Dict]) -> str:
    """Create detailed category context for new field suggestions"""
    context_parts = []
    context_parts.append("AVAILABLE CDD CATEGORIES:")
    
    for cat in categories:
        name = cat.get('name', '')
        display_name = cat.get('display_name', '')
        description = cat.get('description', '')
        
        context_line = f"\n• {name}"
        if display_name and display_name != name:
            context_line += f" ({display_name})"
        if description:
            context_line += f":\n  {description}"
        
        context_parts.append(context_line)
    
    return "\n".join(context_parts)

def create_example_attributes_context(attributes: List[Dict], limit: int = 10) -> str:
    """Create example attributes context for new field suggestions (no truncation of descriptions)"""
    context_parts = []
    context_parts.append("EXAMPLE CDD ATTRIBUTES FOR REFERENCE:")
    # Take a random sample of attributes to show examples
    if len(attributes) > limit:
        sample_attributes = random.sample(attributes, limit)
    else:
        sample_attributes = attributes
    for attr in sample_attributes:
        name = attr.get('name', '')
        display_name = attr.get('display_name', '')
        data_type = attr.get('data_type', '')
        description = attr.get('description', '')
        context_line = f"• {name}"
        if display_name and display_name != name:
            context_line += f" (Label: {display_name})"
        if data_type:
            context_line += f" [Type: {data_type}]"
        if description:
            context_line += f": {description}"
        context_parts.append(context_line)
    return "\n".join(context_parts)

def get_instant_choice(valid_keys, prompt_text):
    """Prompt for a single keypress from valid_keys, allow 'x' to exit."""
    print(prompt_text, end='', flush=True)
    while True:
        key = keyboard.read_key().lower()
        if key == 'x':
            print(f"\n{YELLOW}Exiting by user request...{RESET}")
            sys.exit(0)
        if key in valid_keys:
            print(key)
            # Wait for key release to avoid double reads
            while keyboard.is_pressed(key):
                time.sleep(0.05)
            return key
        # Ignore other keys

def is_field_definition_sufficient(field_name: str, field_definition: str) -> Tuple[bool, str]:
    """Check if field definition has sufficient context for matching"""
    if not field_definition or field_definition.strip() == "":
        return False, "No definition provided"
    
    # Clean the definition first
    cleaned_def = field_definition.strip()
    
    # Remove common non-informative prefixes
    cleaned_def = re.sub(r'^(Confident no match\.?\s*)', '', cleaned_def, flags=re.IGNORECASE)
    cleaned_def = re.sub(r'^(No match found\.?\s*)', '', cleaned_def, flags=re.IGNORECASE)
    cleaned_def = re.sub(r'^(NEED REVIEW\.?\s*)', '', cleaned_def, flags=re.IGNORECASE)
    cleaned_def = cleaned_def.strip()
    
    # Check for insufficient context indicators
    insufficient_indicators = [
        "need review",
        "tbd", "to be determined", "to be defined",
        "unknown", "unclear", "not defined", "not specified",
        "missing", "no description", "no definition",
        "placeholder", "temp", "temporary"
    ]
    
    if any(indicator in cleaned_def.lower() for indicator in insufficient_indicators):
        return False, f"Definition contains insufficient context indicator: '{cleaned_def}'"
    
    # Check minimum length (very short definitions are likely insufficient)
    if len(cleaned_def) < 10:
        return False, f"Definition too short to be meaningful: '{cleaned_def}'"
    
    # Check if definition is just the field name repeated
    if cleaned_def.lower() == field_name.lower():
        return False, "Definition is just the field name repeated"
    
    return True, cleaned_def

def find_best_cdd_matches(field_name: str, field_definition: str, attributes: List[Dict]) -> List[Dict]:
    """Use GPT-4 to find top 3 best matching CDD fields"""
    # First, check if the field definition has sufficient context
    is_sufficient, result = is_field_definition_sufficient(field_name, field_definition)
    
    if not is_sufficient:
        print(f"{YELLOW}⚠️  Insufficient context for field '{field_name}': {result}{RESET}")
        print(f"{YELLOW}   Skipping AI matching to avoid hallucination{RESET}")
        return []
    
    # Use the cleaned definition from validation
    field_definition = result
    
    # Clean, concise prompt with all relevant context
    cdd_context = create_optimized_matching_context(attributes)
    prompt = f"""
You are an expert in financial data mapping and ALM (Asset Liability Management) systems.

Field to Match:
- Name: {field_name}
- Definition: {field_definition}

Available CDD Attributes:
{cdd_context}

Instructions:
1. Find the top 3 best matches from the CDD attributes for this field.
2. Consider semantic similarity between field names, display names (in quotes), and descriptions
3. Pay attention to data types [in brackets] - ensure compatibility (e.g., dates should match dates, strings with strings)
4. Consider the business context and category (in parentheses) - financial/ALM fields should match similar contexts
5. Include confidence scores (0.0 to 1.0) based on:
   - Name/display name similarity (30%)
   - Definition/description semantic match (50%) 
   - Data type compatibility (10%)
   - Category/business context fit (10%)
6. Only suggest matches that are highly likely to be semantically equivalent or very closely related
7. Return results as a JSON array with fields: name, confidence_score, reasoning
8. If you cannot find any highly confident matches (>0.5), return an empty array
9. Prioritize exact or near-exact semantic matches over partial matches

Focus on semantic meaning and financial/ALM relevance rather than exact string matching.

Response format:
[
  {{"name": "cdd_field_name", "confidence_score": 0.95, "reasoning": "Brief explanation covering name, definition, data type, and context match"}},
  ...
]
"""
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a financial data mapping expert specializing in ALM and banking systems. Provide only valid JSON response."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.1
        )
        
        result = response.choices[0].message.content.strip()
        matches = json.loads(result)
        
        # Save prompt and response to fixed file
        output_file = os.path.join(os.path.dirname(__file__), "..", "prompts_out", "matching_prompt.txt")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        save_prompt_and_response(prompt, output_file, result)
        
        return matches
        
    except Exception as e:
        print(f"{RED}Error finding CDD matches: {e}{RESET}")
        # Save failed prompt for debugging
        output_file = os.path.join(os.path.dirname(__file__), "..", "prompts_out", "matching_prompt.txt")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        save_prompt_and_response(prompt, output_file, f"ERROR: {str(e)}")
        return []

def parse_json_response(response_text: str) -> Optional[Dict]:
    """Parse JSON from model response, handling various formats including markdown code blocks"""
    if not response_text:
        return None
    
    # Clean the response text
    cleaned = response_text.strip()
    
    # Try parsing as-is first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code blocks
    # Look for JSON in ```json blocks
    json_block_match = re.search(r'```json\s*\n?(.*?)\n?```', cleaned, re.DOTALL)
    if json_block_match:
        try:
            return json.loads(json_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # Look for JSON in ``` blocks (without language specifier)
    code_block_match = re.search(r'```\s*\n?(.*?)\n?```', cleaned, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # Look for anything that looks like JSON (starts with { and ends with })
    json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0).strip())
        except json.JSONDecodeError:
            pass
    
    # If all else fails, try to find lines that look like JSON and join them
    lines = cleaned.split('\n')
    json_lines = []
    in_json = False
    
    for line in lines:
        line = line.strip()
        if line.startswith('{'):
            in_json = True
            json_lines.append(line)
        elif in_json:
            json_lines.append(line)
            if line.endswith('}'):
                break
    
    if json_lines:
        try:
            return json.loads('\n'.join(json_lines))
        except json.JSONDecodeError:
            pass
    
    return None

def create_new_cdd_field_suggestion(field_name: str, field_definition: str, categories: List[Dict], attributes: List[Dict], cdd_guidelines: str, tag: str = None, feedback_history: str = "", iteration: int = 1) -> Optional[Dict]:
    """Use GPT-4 to suggest a new CDD field with interactive feedback"""
    if tag is None:
        tag = settings.DEFAULT_LABEL_TAG
    
    category_context = create_rich_category_context(categories)
    # Only a sample of attributes for format reference
    example_context = create_example_attributes_context(attributes, limit=8)
    feedback_context = ""
    if feedback_history:
        feedback_context = f"\n\nPREVIOUS FEEDBACK AND REVISIONS:\n{feedback_history}\n\nPlease address the feedback in your new suggestion."
    prompt = f"""
You are an expert in financial data mapping and CDD (Common Data Dictionary) design.

Field to Create:
- Name: {field_name}
- Definition: {field_definition}

Available CDD Categories:
{category_context}

Example CDD Attributes (for format reference only):
{example_context}

CDD Guidelines:
{cdd_guidelines}
{feedback_context}

Instructions:
1. Create a new CDD field suggestion following the guidelines.
2. Choose the most appropriate existing category from the list above based on the field's business purpose.
3. Create a camelCase field name following naming conventions (descriptive, <64 chars, no acronyms unless standard).
4. Suggest appropriate data type based on the field definition:
   - STRING for text, names, descriptions, codes
   - DECIMAL for rates, percentages, amounts, prices
   - DATE for dates
   - BOOLEAN for true/false flags
   - INTEGER for counts, whole numbers
5. Create a clear, professional description following the guidelines (avoid jargon, be specific).
6. Create a user-friendly display label (proper capitalization, spaces, readable).

Return ONLY a valid JSON object with these exact fields:
{{
  "Category": "categoryName",
  "Attribute": "newFieldName",
  "Description": "Professional description following guidelines",
  "Label": "User-Friendly Display Name",
  "Tag": "{tag}",
  "New-Update-Deprecate": "New",
  "Partition Key Order": "",
  "Index Key": "",
  "data_type": "STRING"
}}
"""
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a CDD design expert. Return ONLY a valid JSON object with no markdown formatting or extra text."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.1
        )
        
        result = response.choices[0].message.content.strip()
        
        # Save prompt and response to fixed file
        output_file = os.path.join(os.path.dirname(__file__), "..", "prompts_out", "field_suggestion_prompt.txt")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        save_prompt_and_response(prompt, output_file, result)
        
        # Use dynamic JSON parsing
        suggestion = parse_json_response(result)
        if suggestion:
            return suggestion
        else:
            print(f"{RED}Could not parse JSON from response{RESET}")
            print(f"{WHITE}Raw response: {result}{RESET}")
            return None
        
    except Exception as e:
        print(f"{RED}Error creating new field suggestion: {e}{RESET}")
        # Save failed prompt for debugging
        output_file = os.path.join(os.path.dirname(__file__), "..", "prompts_out", "field_suggestion_prompt.txt")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        save_prompt_and_response(prompt, output_file, f"ERROR: {str(e)}")
        return None

def interactive_new_field_creation(field_name: str, field_definition: str, categories: List[Dict], attributes: List[Dict], cdd_guidelines: str, tag: str = None) -> Optional[Dict]:
    """Interactive process for creating new CDD field with feedback loop"""
    if tag is None:
        tag = settings.DEFAULT_LABEL_TAG
    
    feedback_history = ""
    iteration = 1
    while iteration <= 3:  # Max 3 iterations
        print(f"\n{YELLOW}=== Creating New Field Suggestion (Iteration {iteration}) ==={RESET}")
        suggestion = create_new_cdd_field_suggestion(field_name, field_definition, categories, attributes, cdd_guidelines, tag, feedback_history, iteration)
        if not suggestion:
            print(f"{RED}Failed to create suggestion{RESET}")
            return None
        # Display the suggestion
        print(f"\n{GREEN}Suggested New CDD Field:{RESET}")
        print(f"{WHITE}Category: {suggestion.get('Category', '')}{RESET}")
        print(f"{WHITE}Attribute: {suggestion.get('Attribute', '')}{RESET}")
        print(f"{WHITE}Description: {suggestion.get('Description', '')}{RESET}")
        print(f"{WHITE}Label: {suggestion.get('Label', '')}{RESET}")
        print(f"{WHITE}Data Type: {suggestion.get('data_type', '')}{RESET}")
        # Use instant key selection
        choice = get_instant_choice(['a', 'f', 's'], f"\n{WHITE}Options: [a]ccept, [f]eedback for changes, [s]kip field, [x] to exit: {RESET}")
        if choice == 'a':
            return suggestion
        elif choice == 's':
            return None
        elif choice == 'f':
            print(f"{WHITE}Type feedback and press Enter (or 'x' to exit): {RESET}", end='', flush=True)
            feedback = input().strip()
            if feedback.lower() == 'x':
                print(f"\n{YELLOW}Exiting by user request...{RESET}")
                sys.exit(0)
            if feedback:
                feedback_history += f"\nIteration {iteration}: {feedback}"
                iteration += 1
            else:
                print(f"{WHITE}No feedback provided, accepting current suggestion{RESET}")
                return suggestion
        else:
            print(f"{WHITE}Invalid choice, accepting current suggestion{RESET}")
            return suggestion
    print(f"{YELLOW}Maximum iterations reached, using last suggestion{RESET}")
    return suggestion

def get_cdd_field_info(field_name: str, attributes: List[Dict]) -> Optional[Dict]:
    """Get detailed information about a CDD field"""
    for attr in attributes:
        if attr.get('name') == field_name:
            return attr
    return None

def filter_processable_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to only fields that need processing"""
    field_col = StandardFieldHeaders.FIELD_NAME.value
    context_col = StandardFieldHeaders.CONTEXT_DEFINITION.value
    confirmed_col = StandardFieldHeaders.CDD_CONFIRMED.value
    best_guess_col = StandardFieldHeaders.CDD_BEST_GUESS.value
    
    # Skip fields where:
    # 1. cdd_confirmed is populated (not empty/NaN)
    # 2. cdd_best_guess is populated with any non-empty value (including CDD field names)
    # 3. context_definition contains "NEED REVIEW" (case-insensitive)
    # 4. field_name or context_definition is empty/invalid
    skip_mask = (
        # Already confirmed or processed
        (df[confirmed_col].notna() & (df[confirmed_col].astype(str).str.strip() != "")) |
        (df[best_guess_col].notna() & (df[best_guess_col].astype(str).str.strip() != "")) |
        # Contains "NEED REVIEW" in definition
        (df[context_col].astype(str).str.contains("NEED REVIEW", case=False, na=False)) |
        # Missing or invalid field name/definition
        (df[field_col].isna() | (df[field_col].astype(str).str.strip() == "")) |
        (df[context_col].isna() | (df[context_col].astype(str).str.strip() == ""))
    )
    
    processable: pd.DataFrame = df.loc[~skip_mask].copy()
    
    # Count different skip reasons for reporting
    need_review_count = df[df[context_col].astype(str).str.contains("NEED REVIEW", case=False, na=False)].shape[0]
    already_processed_count = df[
        (df[confirmed_col].notna() & (df[confirmed_col].astype(str).str.strip() != "")) |
        (df[best_guess_col].notna() & (df[best_guess_col].astype(str).str.strip() != ""))
    ].shape[0]
    missing_data_count = df[
        (df[field_col].isna() | (df[field_col].astype(str).str.strip() == "")) |
        (df[context_col].isna() | (df[context_col].astype(str).str.strip() == ""))
    ].shape[0]
    
    print(f"{WHITE}Found {len(processable)} fields to process out of {len(df)} total fields{RESET}")
    print(f"{WHITE}Skipped {len(df) - len(processable)} fields:{RESET}")
    if already_processed_count > 0:
        print(f"{WHITE}  - {already_processed_count} already confirmed/processed{RESET}")
    if need_review_count > 0:
        print(f"{YELLOW}  - {need_review_count} marked as 'NEED REVIEW'{RESET}")
    if missing_data_count > 0:
        print(f"{YELLOW}  - {missing_data_count} with missing field name or definition{RESET}")
    
    return processable

def update_input_file_with_mapping(df: pd.DataFrame, row_index, cdd_field_name: str, input_file_path: str):
    """Update the original DataFrame with the CDD mapping and save immediately"""
    best_guess_col = StandardFieldHeaders.CDD_BEST_GUESS.value
    field_name_col = StandardFieldHeaders.FIELD_NAME.value
    df.at[row_index, best_guess_col] = str(cdd_field_name)
    print(f"{GREEN}Set: {df.at[row_index, field_name_col]} → {cdd_field_name}{RESET}")
    
    # Save immediately after each update
    save_updated_input_file(df, input_file_path)

def save_updated_input_file(df: pd.DataFrame, original_file_path: str):
    """Save the updated input file with CDD mappings"""
    try:
        if original_file_path.lower().endswith('.json'):
            df.to_json(original_file_path, orient='records', indent=2)
        else:
            df.to_csv(original_file_path, index=False)
        print(f"{GREEN}✓ Updated input file saved: {original_file_path}{RESET}")
    except Exception as e:
        print(f"{RED}✗ Error saving updated input file: {e}{RESET}")

def save_single_new_field_request(suggestion: Dict, output_file_path: str):
    """Save a single new field request immediately to the output file"""
    # Add the required columns with correct names
    suggestion["New - Update - Deprecate (NOTE: ALWAYS NEW FOR NOW)"] = "New"
    suggestion["Partition Key Order (NOTE: LEAVE EMPTY FOR NOW)"] = ""
    suggestion["Index Key (NOTE: LEAVE EMPTY FOR NOW)"] = ""
    
    # Create DataFrame with exact column names from SAMPLE_SUGGESTED_CDD_OUTPUT.csv
    required_columns = [
        "Category", 
        "Attribute", 
        "Description", 
        "Label", 
        "Tag", 
        "New - Update - Deprecate (NOTE: ALWAYS NEW FOR NOW)", 
        "Partition Key Order (NOTE: LEAVE EMPTY FOR NOW)", 
        "Index Key (NOTE: LEAVE EMPTY FOR NOW)"
    ]
    
    # Ensure all required columns exist
    for col in required_columns:
        if col not in suggestion:
            suggestion[col] = ""
    
    new_df = pd.DataFrame([suggestion])
    new_df = new_df[required_columns]
    
    # Check if output file exists and merge/append
    if os.path.exists(output_file_path):
        try:
            if output_file_path.lower().endswith('.json'):
                existing_df = pd.read_json(output_file_path)
            else:
                existing_df = pd.read_csv(output_file_path)
            print(f"{WHITE}Appending to existing output file with {len(existing_df)} records{RESET}")
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        except Exception as e:
            print(f"{YELLOW}Could not read existing output file, creating new: {e}{RESET}")
            combined_df = new_df
    else:
        print(f"{WHITE}Creating new output file: {output_file_path}{RESET}")
        combined_df = new_df
    
    # Save to file
    try:
        if output_file_path.lower().endswith('.json'):
            combined_df.to_json(output_file_path, orient='records', indent=2)
        else:
            combined_df.to_csv(output_file_path, index=False)
        print(f"{GREEN}✓ New field request saved to: {output_file_path}{RESET}")
        print(f"{WHITE}Total records in output file: {len(combined_df)}{RESET}")
    except Exception as e:
        print(f"{RED}✗ Error saving new field request: {e}{RESET}")

def main():
    """Main interactive function"""
    print(f"{WHITE}=== CDD Mapping Tool ==={RESET}")
    print(f"{WHITE}This tool will:{RESET}")
    print(f"{WHITE}1. Read your input file from: {INPUT_FILE_PATH}{RESET}")
    print(f"{WHITE}2. Skip fields with cdd_confirmed populated{RESET}")
    print(f"{WHITE}3. Skip fields with cdd_best_guess = SKIP or NEW_FIELD_REQUESTED{RESET}")
    print(f"{WHITE}4. Find matches in existing CDD attributes{RESET}")
    print(f"{WHITE}5. Update cdd_best_guess with matches or NEW_FIELD_REQUESTED{RESET}")
    print(f"{WHITE}6. Create new field requests in: {OUTPUT_FILE_PATH}{RESET}")
    print(f"{WHITE}Press 'q' at any time to quit{RESET}")
    
    # Test database connection
    try:
        test_result = db_client.test_connection()
        if not test_result:
            print(f"{RED}Database connection failed. Please check your connection settings.{RESET}")
            sys.exit(1)
    except Exception as e:
        print(f"{RED}Database connection error: {e}{RESET}")
        sys.exit(1)
    
    # Load all CDD data from database in one call
    cdd_attributes, cdd_categories = get_all_cdd_data_from_db()
    cdd_guidelines = load_cdd_guidelines()
    
    # Load and validate input file
    df = load_input_file(INPUT_FILE_PATH)
    
    # Filter to processable fields only
    processable_df = filter_processable_fields(df)
    if len(processable_df) == 0:
        print(f"{WHITE}No fields need processing!{RESET}")
        return
    
    # Process each field
    field_col = StandardFieldHeaders.FIELD_NAME.value
    context_col = StandardFieldHeaders.CONTEXT_DEFINITION.value
    mappings_made = 0
    
    for idx, (index, row) in enumerate(processable_df.iterrows()):
        field_name = str(row[field_col])
        field_definition = str(row[context_col])
        
        print(f"\n{WHITE}=== Processing Field {idx + 1}/{len(processable_df)} ==={RESET}")
        print(f"{WHITE}Field: {field_name}{RESET}")
        print(f"{WHITE}Definition: {field_definition}{RESET}")
        
        # Check for quit
        if keyboard.is_pressed('q'):
            print(f"{YELLOW}Quitting...{RESET}")
            break
        
        # Find matches (this will handle insufficient context internally)
        matches = find_best_cdd_matches(field_name, field_definition, cdd_attributes)
        
        if matches and len(matches) > 0:
            print(f"\n{GREEN}Found {len(matches)} potential matches:{RESET}")
            for i, match in enumerate(matches, 1):
                cdd_info = get_cdd_field_info(match['name'], cdd_attributes)
                category = cdd_info.get('category', 'Unknown') if cdd_info else 'Unknown'
                print(f"{WHITE}  {i}. {match['name']} (confidence: {match['confidence_score']:.2f}) [Category: {category}]{RESET}")
                # Only show the attribute's description, not reasoning
                if cdd_info and cdd_info.get('description'):
                    desc = cdd_info['description']
                    print(f"{WHITE}     Description: {desc}{RESET}")
            
            valid_keys = [str(i+1) for i in range(len(matches))] + ['n', 's']
            choice = get_instant_choice(valid_keys, f"\n{WHITE}Select: [1-{len(matches)}] to accept match, [n] for new field, [s] to skip, [x] to exit: {RESET}")
            if choice == 's':
                update_input_file_with_mapping(df, index, "SKIP", INPUT_FILE_PATH)
                continue
            elif choice == 'n':
                suggestion = interactive_new_field_creation(field_name, field_definition, cdd_categories, cdd_attributes, cdd_guidelines)
                if suggestion:
                    # Save immediately instead of adding to list
                    save_single_new_field_request(suggestion, OUTPUT_FILE_PATH)
                    update_input_file_with_mapping(df, index, "NEW_FIELD_REQUESTED", INPUT_FILE_PATH)
                    print(f"{GREEN}New field request added{RESET}")
                else:
                    update_input_file_with_mapping(df, index, "SKIP", INPUT_FILE_PATH)
            else:
                try:
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(matches):
                        selected_match = matches[choice_idx]
                        update_input_file_with_mapping(df, index, selected_match['name'], INPUT_FILE_PATH)
                        mappings_made += 1
                    else:
                        print(f"{RED}Invalid choice, skipping field{RESET}")
                        update_input_file_with_mapping(df, index, "SKIP", INPUT_FILE_PATH)
                        continue
                except ValueError:
                    print(f"{RED}Invalid choice, skipping field{RESET}")
                    update_input_file_with_mapping(df, index, "SKIP", INPUT_FILE_PATH)
                    continue
        else:
            # Check if no matches due to insufficient context
            is_sufficient, _ = is_field_definition_sufficient(field_name, field_definition)
            
            if not is_sufficient:
                print(f"{YELLOW}Skipping field due to insufficient context - marked as SKIP{RESET}")
                update_input_file_with_mapping(df, index, "SKIP", INPUT_FILE_PATH)
            else:
                print(f"{YELLOW}No confident matches found. Creating new field suggestion...{RESET}")
                suggestion = interactive_new_field_creation(field_name, field_definition, cdd_categories, cdd_attributes, cdd_guidelines)
                if suggestion:
                    # Save immediately instead of adding to list
                    save_single_new_field_request(suggestion, OUTPUT_FILE_PATH)
                    update_input_file_with_mapping(df, index, "NEW_FIELD_REQUESTED", INPUT_FILE_PATH)
                    print(f"{GREEN}New field request added{RESET}")
                else:
                    update_input_file_with_mapping(df, index, "SKIP", INPUT_FILE_PATH)
    
    # Save results
    print(f"\n{WHITE}=== Processing Complete! ==={RESET}")
    print(f"{WHITE}CDD Mappings made: {mappings_made}{RESET}")
    
    # Save updated input file
    save_choice = get_instant_choice(['y', 'n'], f"{WHITE}Save updated input file? [y/n, x to exit]: {RESET}")
    if save_choice == 'y':
        save_updated_input_file(df, INPUT_FILE_PATH)

if __name__ == "__main__":
    main() 