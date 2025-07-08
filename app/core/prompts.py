"""
Centralized prompt management for the CDD Field Mapping Agent.

This module contains all LLM prompts used throughout the application,
providing a single source of truth for prompt templates and system messages.
"""

import os
from typing import List, Dict, Optional
from app.config import settings


class PromptTemplates:
    """Centralized collection of all LLM prompt templates"""
    
    # System messages for different AI roles
    SYSTEM_MESSAGES = {
        "field_matching_expert": "You are a CDD field matching expert. Return ONLY valid JSON array.",
        "cdd_design_expert": "You are a CDD design expert. Return ONLY a valid JSON object with no markdown formatting or extra text.",
        "financial_data_expert": "You are a financial data mapping expert specializing in ALM and banking systems. Provide only valid JSON response.",
        "description_compression_expert": "You are an expert at compressing technical descriptions while preserving essential meaning.",
        "cdd_field_expert": "You are a financial data expert specializing in CDD design. Provide only valid JSON response."
    }
    
    # Core prompt templates
    FIELD_MATCHING_PROMPT = """You are an expert in financial data mapping and CDD (Common Data Dictionary) field matching.

Field to Match:
- Name: {field_name}
- Definition: {field_definition}

{context}

{feedback_section}

INSTRUCTIONS:
1. Find the best matching CDD attributes for the given field
2. Consider semantic similarity between field names, display names, and descriptions
3. Pay attention to data types - ensure compatibility (e.g., dates should match dates, strings with strings)
4. Consider the business context and category - financial/ALM fields should match similar contexts
5. Return up to {max_matches} best matches
6. Include confidence scores (0.0 to 1.0) based on:
   - Name/display name similarity (30%)
   - Definition/description semantic match (50%) 
   - Data type compatibility (10%)
   - Category/business context fit (10%)
7. Only include matches with confidence > 0.3
8. Prioritize exact or near-exact semantic matches over partial matches

Return JSON array of matches:
[
    {{
        "cdd_field": "attributeName",
        "confidence_score": 0.85,
        "reasoning": "Brief explanation covering name, definition, data type, and context match"
    }}
]"""

    FIELD_MATCHING_PROMPT_ALM = """You are an expert in financial data mapping and ALM (Asset Liability Management) systems.

Field to Match: {field_name}
Field Definition: {field_definition}

{feedback_section}

Available CDD Attributes:
{context}

INSTRUCTIONS:
1. Find the top 3 BEST matches from the CDD attributes for this field
2. ONLY suggest matches that are highly likely to be semantically equivalent or very closely related
3. Consider both the field name and the definition/description when matching
4. For each match, provide a confidence score from 0.0 to 1.0
5. Return results as JSON array with fields: name, confidence_score, reasoning
6. If you cannot find any highly confident matches (>0.5), return empty array

Focus on semantic meaning and financial/ALM relevance rather than exact string matching.

Response format:
[
    {{"name": "cdd_field_name", "confidence_score": 0.95, "reasoning": "explanation"}},
    {{"name": "cdd_field_name", "confidence_score": 0.85, "reasoning": "explanation"}}
]"""

    NEW_FIELD_CREATION_PROMPT = """You are an expert in financial data mapping and CDD design.

Field to Create:
- Name: {field_name}
- Definition: {field_definition}

Available CDD Categories:
{category_context}

CDD Guidelines:
{cdd_guidelines}

{feedback_section}

Task: Create a new CDD field suggestion following the guidelines above.
- Choose appropriate category from the list based on business purpose
- Use camelCase naming (descriptive, <64 chars, avoid acronyms)
- Select correct data type: STRING (text/codes), DECIMAL (rates/amounts), DATE, BOOLEAN (is/has prefixes), INTEGER (counts)
- Write clear, professional description avoiding jargon
- Create user-friendly display label

Return ONLY valid JSON:
{{"Category": "categoryName", "Attribute": "newFieldName", "Description": "Professional description", "Label": "Display Name", "Tag": "{tag}", "New-Update-Deprecate": "New", "Partition Key Order": "", "Index Key": "", "data_type": "STRING"}}"""

    NEW_FIELD_CREATION_PROMPT_ALM = """You are an expert in financial data mapping and CDD (Common Data Dictionary) design.

Field to Create: {field_name}
Field Definition: {field_definition}

{feedback_section}

Available CDD Categories:
{category_context}

CDD Guidelines:
{cdd_guidelines}

INSTRUCTIONS:
1. Create a new CDD field suggestion following the guidelines
2. Choose the most appropriate existing category or suggest a new one
3. Create a camelCase field name following naming conventions
4. Suggest appropriate data type based on the field definition
5. Create clear, professional description
6. Create user-friendly display label

Return JSON response with fields:
- category: technical category name
- attribute: new camelCase attribute name
- description: professional description
- label: user-friendly display name
- data_type: suggested data type (STRING, DECIMAL, INTEGER, DATE, BOOLEAN, AMOUNT, TIMESTAMP)

Response format:
{{
    "category": "instrumentReference",
    "attribute": "newFieldName",
    "description": "Clear professional description...",
    "label": "Display Name",
    "data_type": "STRING"
}}"""

    DESCRIPTION_COMPRESSION_PROMPT = """Make this description shorter by removing unnecessary words. Think shorthand definition - keep only essential words that preserve the core meaning.

Field Context:
- Name: {field_name}
- Data Type: {data_type}
- Display Name: {display_name}

Original Description: {description}

Remove redundant words, articles, and verbose phrases while keeping:
- Core meaning
- Acronym definitions (e.g., "Metropolitan Statistical Area (MSA)" - keep full expansion)
- Technical terms that need explanation
- Data type hints (if not obvious from context)
- Valid values (if critical)
- Business context (if essential)

IMPORTANT: Do not remove acronym expansions or technical term definitions even if they appear in the field name - these provide valuable context for users.

Return ONLY the shortened description with unnecessary words removed."""

    # Bulk processing prompt for multiple fields at once
    BULK_FIELD_MATCHING_PROMPT = """You are an expert in financial data mapping and CDD (Common Data Dictionary) field matching.

Fields to Match ({field_count} fields):
{fields_list}

{context}

{feedback_section}

INSTRUCTIONS:
1. Find the best matching CDD attributes for EACH field listed above
2. Process all fields in a single response to optimize performance
3. Consider semantic similarity between field names, display names, and descriptions
4. Pay attention to data types - ensure compatibility (e.g., dates should match dates, strings with strings)
5. Consider the business context and category - financial/ALM fields should match similar contexts
6. Return up to {max_matches} best matches per field
7. Include confidence scores (0.0 to 1.0) based on:
   - Name/display name similarity (30%)
   - Definition/description semantic match (50%) 
   - Data type compatibility (10%)
   - Category/business context fit (10%)
8. Only include matches with confidence > 0.3
9. Prioritize exact or near-exact semantic matches over partial matches

Return JSON object with results for each field:
{{
    "field_1": [
        {{
            "cdd_field": "attributeName",
            "confidence_score": 0.85,
            "reasoning": "Brief explanation covering name, definition, data type, and context match"
        }}
    ],
    "field_2": [
        {{
            "cdd_field": "attributeName",
            "confidence_score": 0.75,
            "reasoning": "Brief explanation covering name, definition, data type, and context match"
        }}
    ]
}}

IMPORTANT: 
- Use the exact field names as keys in the JSON response
- If no good matches found for a field, return empty array for that field
- Ensure all {field_count} fields are included in the response"""

    # CLI-specific prompts with more detailed instructions
    CLI_FIELD_MATCHING_PROMPT = """You are an expert in financial data mapping and ALM (Asset Liability Management) systems.

Field to Match:
- Name: {field_name}
- Definition: {field_definition}

Available CDD Attributes:
{context}

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
]"""

    CLI_NEW_FIELD_CREATION_PROMPT = """You are an expert in financial data mapping and CDD (Common Data Dictionary) design.

Field to Create:
- Name: {field_name}
- Definition: {field_definition}

Available CDD Categories:
{category_context}

Example CDD Attributes (for format reference only):
{example_context}

CDD Guidelines:
{cdd_guidelines}{feedback_context}

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
}}"""


class PromptBuilder:
    """Builder class for constructing prompts with context and parameters"""
    
    def __init__(self):
        self.cdd_guidelines = self._load_cdd_guidelines()
    
    def _load_cdd_guidelines(self) -> str:
        """Load CDD guidelines from file"""
        try:
            # Try the main guidelines file first
            guidelines_path = os.path.join(os.path.dirname(__file__), "..", "prompt.txt")
            if os.path.exists(guidelines_path):
                with open(guidelines_path, 'r') as f:
                    return f.read().strip()
            
            # Fallback to context directory
            context_path = os.path.join(os.path.dirname(__file__), "..", "..", "context", "guidelines_for_adding_to_cdd.txt")
            if os.path.exists(context_path):
                with open(context_path, 'r') as f:
                    return f.read().strip()
            
            return "CDD guidelines not found"
        except Exception as e:
            print(f"Error loading CDD guidelines: {e}")
            return "CDD guidelines not available"
    
    def build_field_matching_prompt(self, field_name: str, field_definition: str, context: str, max_matches: int = 3, use_alm_format: bool = False, feedback_text: Optional[str] = None) -> str:
        """Build a field matching prompt"""
        # Create feedback section
        feedback_section = ""
        if feedback_text:
            feedback_section = f"""
USER FEEDBACK FOR IMPROVEMENT:
{feedback_text}

Please take this feedback into account when finding matches and adjust your search criteria accordingly.
"""
        
        if use_alm_format:
            return PromptTemplates.FIELD_MATCHING_PROMPT_ALM.format(
                field_name=field_name,
                field_definition=field_definition,
                context=context,
                feedback_section=feedback_section
            )
        else:
            return PromptTemplates.FIELD_MATCHING_PROMPT.format(
                field_name=field_name,
                field_definition=field_definition,
                context=context,
                max_matches=max_matches,
                feedback_section=feedback_section
            )
    
    def build_cli_field_matching_prompt(self, field_name: str, field_definition: str, context: str) -> str:
        """Build a CLI-specific field matching prompt"""
        return PromptTemplates.CLI_FIELD_MATCHING_PROMPT.format(
            field_name=field_name,
            field_definition=field_definition,
            context=context
        )
    
    def build_new_field_creation_prompt(self, field_name: str, field_definition: str, category_context: str, tag: Optional[str] = None, feedback_text: Optional[str] = None, use_alm_format: bool = False) -> str:
        """Build a new field creation prompt"""
        if tag is None:
            tag = settings.DEFAULT_LABEL_TAG
        
        # Create feedback section
        feedback_section = ""
        if feedback_text:
            feedback_section = f"""
USER FEEDBACK FOR IMPROVEMENT:
{feedback_text}

Please take this feedback into account when creating the new field suggestion and adjust your response accordingly.
"""
        
        if use_alm_format:
            return PromptTemplates.NEW_FIELD_CREATION_PROMPT_ALM.format(
                field_name=field_name,
                field_definition=field_definition,
                category_context=category_context,
                cdd_guidelines=self.cdd_guidelines,
                feedback_section=feedback_section
            )
        else:
            return PromptTemplates.NEW_FIELD_CREATION_PROMPT.format(
                field_name=field_name,
                field_definition=field_definition,
                category_context=category_context,
                cdd_guidelines=self.cdd_guidelines,
                feedback_section=feedback_section,
                tag=tag
            )
    
    def build_cli_new_field_creation_prompt(self, field_name: str, field_definition: str, category_context: str, example_context: str, tag: Optional[str] = None, feedback_context: str = "") -> str:
        """Build a CLI-specific new field creation prompt"""
        if tag is None:
            tag = settings.DEFAULT_LABEL_TAG
        
        return PromptTemplates.CLI_NEW_FIELD_CREATION_PROMPT.format(
            field_name=field_name,
            field_definition=field_definition,
            category_context=category_context,
            example_context=example_context,
            cdd_guidelines=self.cdd_guidelines,
            feedback_context=feedback_context,
            tag=tag
        )
    
    def build_description_compression_prompt(self, description: str, field_name: str = "", data_type: str = "", display_name: str = "", max_tokens: Optional[int] = None) -> str:
        """Build a description compression prompt with field context"""
        return PromptTemplates.DESCRIPTION_COMPRESSION_PROMPT.format(
            description=description,
            field_name=field_name or "Unknown",
            data_type=data_type or "Unknown", 
            display_name=display_name or "Unknown"
        )
    
    def build_bulk_field_matching_prompt(self, fields: List[Dict[str, str]], context: str, max_matches: int = 3, feedback_text: Optional[str] = None) -> str:
        """Build a bulk field matching prompt for multiple fields"""
        # Create feedback section
        feedback_section = ""
        if feedback_text:
            feedback_section = f"""
USER FEEDBACK FOR IMPROVEMENT:
{feedback_text}

Please take this feedback into account when finding matches and adjust your search criteria accordingly.
"""
        
        # Format fields list
        fields_list = ""
        for i, field in enumerate(fields, 1):
            fields_list += f"Field {i}: {field['field_name']}\n"
            fields_list += f"  Definition: {field['field_definition']}\n\n"
        
        return PromptTemplates.BULK_FIELD_MATCHING_PROMPT.format(
            field_count=len(fields),
            fields_list=fields_list.strip(),
            context=context,
            max_matches=max_matches,
            feedback_section=feedback_section
        )
    
    def get_system_message(self, role: str) -> str:
        """Get a system message for a specific AI role"""
        return PromptTemplates.SYSTEM_MESSAGES.get(role, "You are a helpful AI assistant.")


# Global prompt builder instance
_prompt_builder = None

def get_prompt_builder() -> PromptBuilder:
    """Get the global prompt builder instance"""
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = PromptBuilder()
    return _prompt_builder


# Convenience functions for common prompt operations
def build_field_matching_prompt(field_name: str, field_definition: str, context: str, max_matches: int = 3, use_alm_format: bool = False, feedback_text: Optional[str] = None) -> str:
    """Build a field matching prompt"""
    return get_prompt_builder().build_field_matching_prompt(field_name, field_definition, context, max_matches, use_alm_format, feedback_text)

def build_new_field_creation_prompt(field_name: str, field_definition: str, category_context: str, tag: Optional[str] = None, feedback_text: Optional[str] = None, use_alm_format: bool = False) -> str:
    """Build a new field creation prompt"""
    return get_prompt_builder().build_new_field_creation_prompt(field_name, field_definition, category_context, tag, feedback_text, use_alm_format)

def build_description_compression_prompt(description: str, field_name: str = "", data_type: str = "", display_name: str = "", max_tokens: Optional[int] = None) -> str:
    """Build a description compression prompt with field context"""
    return get_prompt_builder().build_description_compression_prompt(description, field_name, data_type, display_name, max_tokens)

def get_system_message(role: str) -> str:
    """Get a system message for a specific AI role"""
    return get_prompt_builder().get_system_message(role) 