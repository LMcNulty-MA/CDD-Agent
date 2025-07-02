"""
CDD Mapping Service Layer

This module extracts the core functionality from the CLI tool (cdd_mapping.py) 
to create reusable services for both command-line and web interfaces.
"""

import pandas as pd
import json
import os
import re
from typing import List, Dict, Optional, Tuple, Any

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from app.config import settings
from app.core.documentdb import MongoDBClient
from app.core.models import (
    StandardFieldHeaders, CDDMatchResult, NewCDDFieldSuggestion,
    SingleFieldCheckResponse
)

# Set up OpenAI client if available
if HAS_OPENAI:
    openai.api_key = settings.OPENAI_API_KEY
    client = openai.OpenAI()
else:
    client = None

class CDDMappingService:
    """Core service for CDD field mapping operations"""
    
    def __init__(self, db_client=None):
        self.db_client = db_client or MongoDBClient(settings.DOCDB_URI, settings.DOCDB_DATABASE_NAME)
        self.cdd_guidelines = self._load_cdd_guidelines()
        
    def _load_cdd_guidelines(self) -> str:
        """Load the comprehensive CDD guidelines from context file"""
        guidelines_path = os.path.join(os.path.dirname(__file__), "..", "..", "context", "guidelines_for_adding_to_cdd.txt")
        try:
            with open(guidelines_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
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

    def get_all_cdd_data_from_db(self) -> Tuple[List[Dict], List[Dict]]:
        """Get all CDD attributes and categories from database"""
        try:
            # Get all attributes with no limit
            attributes = self.db_client.get_documents("attributes", {}, limit=0)
            categories = self.db_client.get_documents("categories", {}, limit=0)
            return attributes, categories
        except Exception as e:
            print(f"Error fetching CDD data: {e}")
            return [], []

    def find_best_cdd_matches(self, field_name: str, field_definition: str, cdd_attributes: List[Dict], max_matches: int = 5) -> List[Dict]:
        """Find best CDD matches for a field using GPT-4"""
        if not HAS_OPENAI or not client:
            print("OpenAI not available, returning empty matches")
            return []
        
        # First, check if the field definition has sufficient context
        is_sufficient, result = self._is_field_definition_sufficient(field_name, field_definition)
        
        if not is_sufficient:
            print(f"⚠️  Insufficient context for field '{field_name}': {result}")
            print("   Skipping AI matching to avoid hallucination")
            return []
        
        # Use the cleaned definition from validation
        field_definition = result
        
        # Create context for matching
        context = self._create_optimized_matching_context(cdd_attributes)
        
        prompt = f"""
        You are an expert in financial data mapping and CDD (Common Data Dictionary) field matching.
        
        Field to Match:
        - Name: {field_name}
        - Definition: {field_definition}
        
        {context}
        
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
        ]
        """
        
        try:
            response = client.chat.completions.create(
                model=settings.MODEL_TO_USE,
                messages=[
                    {"role": "system", "content": "You are a CDD field matching expert. Return ONLY valid JSON array."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            matches_data = self._parse_json_response(result)
            
            if not matches_data:
                return []
            
            # Enrich matches with CDD field info
            enriched_matches = []
            for match in matches_data:
                cdd_info = self._get_cdd_field_info(match['cdd_field'], cdd_attributes)
                if cdd_info:
                    enriched_match = {
                        'name': match['cdd_field'],
                        'confidence_score': match['confidence_score'],
                        'reasoning': match.get('reasoning', ''),
                        'description': cdd_info.get('description', ''),
                        'category': cdd_info.get('category', ''),
                        'data_type': cdd_info.get('dataType', ''),  # Database uses camelCase
                        'display_name': cdd_info.get('displayName', '')  # Database uses camelCase
                    }
                    enriched_matches.append(enriched_match)
            
            return sorted(enriched_matches, key=lambda x: x['confidence_score'], reverse=True)
            
        except Exception as e:
            print(f"Error finding matches: {e}")
            return []

    def create_new_cdd_field_suggestion(self, field_name: str, field_definition: str, categories: List[Dict], attributes: List[Dict], tag: Optional[str] = None, feedback_history: str = "") -> Optional[Dict]:
        """Create a new CDD field suggestion using GPT-4"""
        if not HAS_OPENAI or not client:
            print("OpenAI not available, returning no suggestion")
            return None
            
        if tag is None:
            tag = settings.DEFAULT_LABEL_TAG
        
        # Clean the field definition
        field_definition = self._clean_field_definition(field_definition)
        
        category_context = self._create_rich_category_context(categories)
        
        # Add feedback context if provided
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

        CDD Guidelines:
        {self.cdd_guidelines}{feedback_context}

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
                model=settings.MODEL_TO_USE,
                messages=[
                    {"role": "system", "content": "You are a CDD design expert. Return ONLY a valid JSON object with no markdown formatting or extra text."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            return self._parse_json_response(result)
            
        except Exception as e:
            print(f"Error creating new field suggestion: {e}")
            return None

    def _clean_field_definition(self, definition: str) -> str:
        """Clean field definition by removing matching result text and fixing truncation"""
        if not definition:
            return ""
        
        # Remove "Confident no match" and similar text
        definition = re.sub(r'^(Confident no match\.?\s*)', '', definition, flags=re.IGNORECASE)
        definition = re.sub(r'^(No match found\.?\s*)', '', definition, flags=re.IGNORECASE)
        definition = re.sub(r'^(NEED REVIEW\.?\s*)', '', definition, flags=re.IGNORECASE)
        
        # Clean up whitespace
        definition = re.sub(r'\s+', ' ', definition).strip()
        
        return definition

    def _is_field_definition_sufficient(self, field_name: str, field_definition: str) -> Tuple[bool, str]:
        """Check if field definition has sufficient context for matching"""
        if not field_definition or field_definition.strip() == "":
            return False, "No definition provided"
        
        # Clean the definition first
        cleaned_def = self._clean_field_definition(field_definition)
        
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

    def _create_optimized_matching_context(self, attributes: List[Dict]) -> str:
        """Create optimized context for field matching with display names and data types"""
        context_parts = ["AVAILABLE CDD ATTRIBUTES:"]
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

    def _create_rich_category_context(self, categories: List[Dict]) -> str:
        """Create detailed category context for new field suggestions"""
        context_parts = ["AVAILABLE CDD CATEGORIES:"]
        
        for cat in categories:
            name = cat.get('name', '')
            display_name = cat.get('displayName', '')  # Database uses camelCase
            description = cat.get('description', '')
            
            context_line = f"\n• {name}"
            if display_name and display_name != name:
                context_line += f" ({display_name})"
            if description:
                context_line += f":\n  {description}"
            
            context_parts.append(context_line)
        
        return "\n".join(context_parts)

    def _get_cdd_field_info(self, field_name: str, cdd_attributes: List[Dict]) -> Optional[Dict]:
        """Get detailed info for a CDD field"""
        for attr in cdd_attributes:
            if attr.get('name') == field_name:
                return attr
        return None

    def _parse_json_response(self, response: str) -> Optional[Any]:
        """Parse JSON response with fallback for markdown-wrapped JSON"""
        if not response:
            return None
        
        # Remove markdown code blocks if present
        response = re.sub(r'^```(?:json)?\s*', '', response, flags=re.MULTILINE)
        response = re.sub(r'\s*```$', '', response, flags=re.MULTILINE)
        response = response.strip()
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
        
        return None

    def check_single_field(self, field_name: str, field_definition: str, force_new_suggestion: bool = False, feedback_history: Optional[List[Dict]] = None) -> SingleFieldCheckResponse:
        """Check a single field against CDD attributes with optional feedback handling"""
        # Get CDD data
        cdd_attributes, cdd_categories = self.get_all_cdd_data_from_db()
        
        # Clean the definition
        cleaned_definition = self._clean_field_definition(field_definition)
        
        # Convert feedback history to string format for the AI prompt
        feedback_text = ""
        if feedback_history:
            feedback_parts = []
            for item in feedback_history:
                if item.get('action') == 'feedback':
                    feedback_parts.append(f"User feedback: {item.get('feedback', '')}")
                elif item.get('action') == 'generate_new_field':
                    feedback_parts.append(f"User requested new field generation for: {item.get('field_name', '')}")
            feedback_text = "\n".join(feedback_parts)
        
        # Find matches (unless forced to create new suggestion)
        match_results = []
        if not force_new_suggestion:
            matches = self.find_best_cdd_matches(field_name, cleaned_definition, cdd_attributes)
            
            # Convert to response format
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
        
        # Determine status and create new field suggestion if needed
        status = "no_match"
        new_field_suggestion = None
        
        if match_results and match_results[0].confidence_score >= 0.6 and not force_new_suggestion:
            status = "matched"
        else:
            # Create new field suggestion (with feedback if provided)
            suggestion_data = self.create_new_cdd_field_suggestion(
                field_name, cleaned_definition, cdd_categories, cdd_attributes, feedback_history=feedback_text
            )
            if suggestion_data:
                new_field_suggestion = NewCDDFieldSuggestion(
                    category=suggestion_data.get("Category", ""),
                    attribute=suggestion_data.get("Attribute", ""),
                    description=suggestion_data.get("Description", ""),
                    label=suggestion_data.get("Label", ""),
                    tag=suggestion_data.get("Tag", settings.DEFAULT_LABEL_TAG),
                    action=suggestion_data.get("New-Update-Deprecate", "New"),
                    partition_key_order=None,
                    index_key=None,
                    data_type=suggestion_data.get("data_type", "STRING")
                )
                status = "new_suggestion"
        
        return SingleFieldCheckResponse(
            field_name=field_name,
            field_definition=cleaned_definition,
            matches=match_results,
            new_field_suggestion=new_field_suggestion,
            status=status,
            confidence_threshold=0.6
        )


# Create shared service instance
cdd_mapping_service = CDDMappingService() 