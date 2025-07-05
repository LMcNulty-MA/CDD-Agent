"""
CDD Mapping Service Layer

This module extracts the core functionality from the CLI tool (cdd_mapping.py) 
to create reusable services for both command-line and web interfaces.
"""

import pandas as pd
import json
import os
import re
import logging
from datetime import datetime
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
    SingleFieldCheckResponse, DescriptionCompressionResponse
)
from app.core.utils import save_prompt_and_response, ProcessLogger
from app.core.prompts import get_prompt_builder, get_system_message

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

    def find_best_cdd_matches(self, field_name: str, field_definition: str, cdd_attributes: List[Dict], max_matches: int = 5, feedback_text: Optional[str] = None) -> List[Dict]:
        """Find best CDD matches for a field using GPT-4 with optional feedback"""
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
        
        # Use centralized prompt builder with feedback
        prompt_builder = get_prompt_builder()
        prompt = prompt_builder.build_field_matching_prompt(
            field_name=field_name,
            field_definition=field_definition,
            context=context,
            max_matches=max_matches,
            use_alm_format=False,
            feedback_text=feedback_text
        )
        
        try:
            # Prepare API call parameters
            api_params = {
                "model": settings.MODEL_TO_USE,
                "messages": [
                    {"role": "system", "content": get_system_message("field_matching_expert")},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1000,
            }
            
            # Only add temperature for models that support it
            if settings.MODEL_TO_USE not in ["gpt-4o-mini", "o1-mini", "o1-preview"]:
                api_params["temperature"] = 0.1
            
            response = client.chat.completions.create(**api_params)
            
            result = response.choices[0].message.content.strip()
            
            # Save prompt and response for debugging (like CLI tool) - only if enabled
            if settings.SAVE_PROMPTS_TO_FILE:
                suffix = "_with_feedback" if feedback_text else ""
                output_file = os.path.join(os.path.dirname(__file__), "..", "..", "prompts_out", f"web_matching_prompt{suffix}.txt")
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                save_prompt_and_response(prompt, output_file, result)
                print(f"💾 Saved matching prompt to: {output_file}")
            
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

    def create_new_cdd_field_suggestion(self, field_name: str, field_definition: str, categories: List[Dict], attributes: List[Dict], tag: Optional[str] = None, feedback_text: Optional[str] = None) -> Optional[Dict]:
        """Create a new CDD field suggestion using GPT-4 with optional feedback"""
        if not HAS_OPENAI or not client:
            print("OpenAI not available, returning no suggestion")
            return None
            
        if tag is None:
            tag = settings.DEFAULT_LABEL_TAG
        
        # Clean the field definition
        field_definition = self._clean_field_definition(field_definition)
        
        category_context = self._create_rich_category_context(categories)
        
        # Use centralized prompt builder with feedback
        prompt_builder = get_prompt_builder()
        prompt = prompt_builder.build_new_field_creation_prompt(
            field_name=field_name,
            field_definition=field_definition,
            category_context=category_context,
            tag=tag,
            feedback_text=feedback_text,
            use_alm_format=False
        )
        
        try:
            response = client.chat.completions.create(
                model=settings.MODEL_TO_USE,
                messages=[
                    {"role": "system", "content": get_system_message("cdd_design_expert")},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            
            # Save prompt and response for debugging (like CLI tool) - only if enabled
            if settings.SAVE_PROMPTS_TO_FILE:
                suffix = "_with_feedback" if feedback_text else ""
                output_file = os.path.join(os.path.dirname(__file__), "..", "..", "prompts_out", f"web_field_suggestion_prompt{suffix}.txt")
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                save_prompt_and_response(prompt, output_file, result)
                print(f"💾 Saved field suggestion prompt to: {output_file}")
            
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
        """Create optimized context for field matching with abbreviated format"""
        # Category abbreviations to save tokens
        category_abbrevs = {
            'instrumentReference': 'InstRef',
            'entityReference': 'EntRef', 
            'interestRateInput': 'IRInput',
            'accountCashFlow': 'AcctCF',
            'loanPerformance': 'LoanPerf',
            'collateralReference': 'CollRef',
            'regulatoryReference': 'RegRef',
            'marketDataInput': 'MktData',
            'creditRiskInput': 'CreditRisk',
            'operationalRiskInput': 'OpRisk'
        }
        
        # Data type abbreviations
        datatype_abbrevs = {
            'String': 'S',
            'Decimal': 'D', 
            'Date': 'Dt',
            'Boolean': 'B',
            'Integer': 'I'
        }
        
        context_parts = ["AVAILABLE CDD ATTRIBUTES:"]
        for attr in attributes:
            name = attr.get('name', '')
            data_type = attr.get('dataType', '')  # Database uses camelCase
            category = attr.get('category', '')
            description = attr.get('description', '')
            
            # Start with technical name (no display name to save tokens)
            context_line = f"• {name}"
            
            # Add abbreviated data type in brackets
            if data_type:
                abbrev_type = datatype_abbrevs.get(data_type, data_type)
                context_line += f" [{abbrev_type}]"
            
            # Add abbreviated category in parentheses
            if category:
                abbrev_category = category_abbrevs.get(category, category)
                context_line += f" ({abbrev_category})"
            
            # Add description - use compressed version if available, fallback to full description
            compressed_description = attr.get('description_compressed', '')
            if compressed_description:
                context_line += f": {compressed_description}"
            elif description:
                context_line += f": {description}"
                # Log warning about fallback to full description
            
            context_parts.append(context_line)
        return "\n".join(context_parts)

    def _create_rich_category_context(self, categories: List[Dict]) -> str:
        """Create detailed category context for new field suggestions"""
        context_parts = []
        
        for cat in categories:
            name = cat.get('name', '')
            display_name = cat.get('displayName', '')  # Database uses camelCase
            description = cat.get('description', '')
            
            context_line = f"• {name}"
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

    def check_single_field(self, field_name: str, field_definition: str, action_type: str = "find_matches", feedback_text: Optional[str] = None) -> SingleFieldCheckResponse:
        """Check a single field against CDD attributes with feedback support"""
        # Get CDD data
        cdd_attributes, cdd_categories = self.get_all_cdd_data_from_db()
        
        # Clean the definition
        cleaned_definition = self._clean_field_definition(field_definition)
        
        # Handle different action types
        match_results = []
        new_field_suggestion = None
        status = "no_match"
        feedback_applied = bool(feedback_text)
        
        if action_type in ["find_matches", "improve_matches"]:
            # Find matches with optional feedback
            matches = self.find_best_cdd_matches(
                field_name, 
                cleaned_definition, 
                cdd_attributes, 
                feedback_text=feedback_text
            )
            
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
            
            if match_results and match_results[0].confidence_score >= 0.6:
                status = "matched"
            
        elif action_type in ["create_new_field", "improve_new_field"]:
            # Create new field suggestion with optional feedback
            suggestion_data = self.create_new_cdd_field_suggestion(
                field_name, 
                cleaned_definition, 
                cdd_categories, 
                cdd_attributes, 
                feedback_text=feedback_text
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
            confidence_threshold=0.6,
            feedback_applied=feedback_applied
        )

    def compress_attribute_description(self, description: str, field_name: str = "", data_type: str = "", display_name: str = "", max_tokens: Optional[int] = None) -> str:
        """Compress a single attribute description using AI while preserving key information"""
        if not HAS_OPENAI or not client:
            print("OpenAI not available, returning original description")
            return description
        
        word_count = len(description.split())
        
        # Skip very short descriptions - they're already concise enough
        if word_count <= 5:
            return description
        
        # Use centralized prompt builder with field context for better compression
        prompt_builder = get_prompt_builder()
        compression_prompt = prompt_builder.build_description_compression_prompt(
            description=description,
            field_name=field_name,
            data_type=data_type,
            display_name=display_name
        )

        try:
            # Log the request details
            request_logger = ProcessLogger("compression_api_requests.log", auto_clear=False)
            request_logger.info("Sending compression request", context={
                "model": settings.COMPRESSION_MODEL,
                "field_name": field_name or "Unknown",
                "data_type": data_type or "Unknown", 
                "display_name": display_name or "Unknown",
                "input_word_count": word_count,
                "input_preview": description[:150] + "..."
            })
            
            response = client.chat.completions.create(
                model=settings.COMPRESSION_MODEL,
                messages=[
                    {"role": "system", "content": get_system_message("description_compression_expert")},
                    {"role": "user", "content": compression_prompt}
                ]
            )
            
            # Log the raw response
            raw_content = response.choices[0].message.content
            request_logger.info("Received API response", context={
                "raw_response": raw_content,
                "response_type": type(raw_content).__name__,
                "is_none": raw_content is None,
                "is_empty": raw_content == "" if raw_content else "N/A",
                "length": len(raw_content) if raw_content else 0
            })
            
            compressed = raw_content.strip() if raw_content else ""
            
            # Log the processing result
            request_logger.info("Processing response", context={
                "after_strip": compressed,
                "after_strip_length": len(compressed),
                "is_shorter": len(compressed.split()) < len(description.split()) if compressed else False
            })
            
            # Basic validation - make sure it's actually shorter
            if compressed and len(compressed.split()) < len(description.split()):
                request_logger.success("Compression successful", context={
                    "original_words": len(description.split()),
                    "compressed_words": len(compressed.split()),
                    "result": compressed[:100] + "..."
                })
                return compressed
            else:
                request_logger.warning("Compression not shorter, returning original", context={
                    "original_words": len(description.split()),
                    "compressed_words": len(compressed.split()) if compressed else 0,
                    "compressed_result": compressed[:100] + "..." if compressed else "EMPTY"
                })
                return description
                
        except Exception as e:
            # Log detailed error information
            error_msg = f"Error compressing description: {str(e)}"
            print(error_msg)  # Keep console output for immediate feedback
            
            # Log detailed error to dedicated file
            try:
                error_logger = ProcessLogger("compression_api_errors.log", auto_clear=False)
                error_logger.error("API compression failed", context={
                    "error": str(e),
                    "exception_type": type(e).__name__,
                    "original_word_count": word_count,
                    "model": settings.COMPRESSION_MODEL,
                    "description_length_chars": len(description),
                    "description_preview": description[:150] + "..." if len(description) > 150 else description
                })
            except:
                pass  # Don't fail if logging fails
            
            return description

    def compress_all_descriptions(self, batch_size: Optional[int] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Compress all attribute descriptions in the database"""
        if batch_size is None:
            batch_size = settings.COMPRESSION_BATCH_SIZE
        
        # Set up compression logging using ProcessLogger
        logger = ProcessLogger("compression_process.log")
        logger.section("COMPRESSION PROCESS STARTED")
        logger.info("Process configuration", context={
            "batch_size": batch_size, 
            "dry_run": dry_run, 
            "model": settings.COMPRESSION_MODEL
        })
        
        try:
            # Get total count for reporting
            all_attributes, _ = self.get_all_cdd_data_from_db()
            total_attributes_count = len(all_attributes)
            
            # Query MongoDB directly for attributes that need compression:
            # - Has a description (exists and not empty)
            # - Does NOT have a compressed description (field doesn't exist, is null, or is empty)
            query_filter = {
                "description": {"$exists": True, "$ne": "", "$ne": None},
                "$or": [
                    {"description_compressed": {"$exists": False}},
                    {"description_compressed": None},
                    {"description_compressed": ""},
                    {"description_compressed": {"$regex": "^\\s*$"}}  # Empty or only whitespace
                ]
            }
            
            attributes_to_process = self.db_client.get_documents("attributes", query_filter, limit=0)
            
            logger.info("MongoDB query for attributes needing compression", context={
                "total_attributes_in_db": total_attributes_count,
                "attributes_needing_compression": len(attributes_to_process),
                "skipped_count": total_attributes_count - len(attributes_to_process)
            })
            
            stats = {
                'total_processed': 0,
                'compressed_count': 0,
                'failed_count': 0,
                'skipped_count': total_attributes_count - len(attributes_to_process)
            }
            
            preview_samples = []
            
            # Process in batches
            for i in range(0, len(attributes_to_process), batch_size):
                batch = attributes_to_process[i:i + batch_size]
                batch_num = i//batch_size + 1
                total_batches = (len(attributes_to_process) + batch_size - 1)//batch_size
                
                print(f"Processing batch {batch_num}/{total_batches}...")
                logger.info("Processing batch", context={
                    "batch_num": batch_num, 
                    "total_batches": total_batches, 
                    "batch_size": len(batch)
                })
                
                for attr in batch:
                    attr_name = attr.get('name', 'UNKNOWN')
                    original_desc = attr.get('description', '')
                    attr_data_type = attr.get('dataType', '')  # Database uses camelCase
                    attr_display_name = attr.get('displayName', '')  # Database uses camelCase
                    
                    # All filtering already done - these attributes need processing
                    original_word_count = len(original_desc.split())
                    
                    # Compress description with field context
                    logger.info("Compressing attribute", context={
                        "attribute": attr_name, 
                        "original_words": original_word_count,
                        "original_preview": original_desc[:100] + "...",
                        "data_type": attr_data_type,
                        "display_name": attr_display_name
                    })
                    
                    compressed_desc = self.compress_attribute_description(
                        description=original_desc,
                        field_name=attr_name,
                        data_type=attr_data_type,
                        display_name=attr_display_name
                    )
                    stats['total_processed'] += 1
                    
                    # VALIDATE the compressed description - must be shorter and meaningful
                    is_valid_compression = (
                        compressed_desc and  # Not empty
                        compressed_desc.strip() and  # Not just whitespace
                        compressed_desc != original_desc and  # Actually changed
                        len(compressed_desc.split()) < original_word_count  # Actually shorter
                    )
                    
                    if is_valid_compression:
                        compressed_word_count = len(compressed_desc.split())
                        stats['compressed_count'] += 1
                        
                        logger.success("Successfully compressed attribute", context={
                            "attribute": attr_name,
                            "original_words": original_word_count,
                            "compressed_words": compressed_word_count,
                            "reduction": f"{((original_word_count - compressed_word_count) / original_word_count * 100):.1f}%",
                            "compressed_preview": compressed_desc[:100] + "..."
                        })
                        
                        # Store sample for preview
                        if len(preview_samples) < 5:
                            preview_samples.append({
                                'attribute': attr_name,
                                'original': original_desc[:100] + '...' if len(original_desc) > 100 else original_desc,
                                'compressed': compressed_desc
                            })
                        
                        # Update database if not dry run - ADD NEW FIELD, DON'T OVERWRITE
                        if not dry_run:
                            try:
                                logger.info("Saving compressed description to NEW field", context={
                                    "attribute": attr_name,
                                    "action": "adding_compressed_description_field"
                                })
                                self.db_client.update_document(
                                    "attributes", 
                                    {"name": attr_name}, 
                                    {"$set": {"description_compressed": compressed_desc}}  # NEW FIELD!
                                )
                                logger.success("Database updated with compressed description", context={
                                    "attribute": attr_name,
                                    "original_kept": "YES - original description preserved",
                                    "new_field": "description_compressed"
                                })
                            except Exception as e:
                                logger.failure("Database update failed", context={
                                    "attribute": attr_name,
                                    "error": str(e),
                                    "original_preview": original_desc[:100] + "...",
                                    "compressed_preview": compressed_desc[:100] + "..."
                                })
                                stats['failed_count'] += 1
                                stats['compressed_count'] -= 1
                    else:
                        stats['failed_count'] += 1
                        logger.failure("Compression validation failed", context={
                            "attribute": attr_name,
                            "original_words": original_word_count,
                            "compressed_result": compressed_desc[:100] + "..." if compressed_desc else "EMPTY/NULL",
                            "issues": [
                                "Empty result" if not compressed_desc or not compressed_desc.strip() else None,
                                "No change" if compressed_desc == original_desc else None,
                                "Not shorter" if compressed_desc and len(compressed_desc.split()) >= original_word_count else None
                            ]
                        })
            
            # Final summary
            logger.section("COMPRESSION PROCESS COMPLETED")
            logger.info("Final statistics", context={
                "total_attributes_in_db": total_attributes_count,
                "skipped_already_processed": stats['skipped_count'],
                "attempted_compression": stats['total_processed'],
                "successfully_compressed": stats['compressed_count'], 
                "failed_compression": stats['failed_count'],
                "success_rate": f"{(stats['compressed_count'] / max(stats['total_processed'], 1) * 100):.1f}%" if stats['total_processed'] > 0 else "0%"
            })
            
            return {**stats, 'preview_samples': preview_samples}
            
        except Exception as e:
            logger.failure("Critical error in batch compression", context={
                "error": str(e),
                "exception_type": type(e).__name__
            })
            import traceback
            logger.error("Full traceback", context={"traceback": traceback.format_exc()})
            return {'total_processed': 0, 'compressed_count': 0, 'failed_count': 1, 'skipped_count': 0}


# Create shared service instance
cdd_mapping_service = CDDMappingService() 