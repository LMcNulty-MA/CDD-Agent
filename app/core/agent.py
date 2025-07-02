import logging
import openai
from typing import List, Dict, Optional, Tuple
import json
from app.config import settings
from .documentdb import AsyncMongoDBClient
from .models import (
    FieldMappingRequest, 
    FieldMappingResponse, 
    CDDMatchResult, 
    NewCDDFieldSuggestion,
    EnrichedCDDAttribute
)

logger = logging.getLogger(__name__)

# OpenAI client
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

class CDDMappingAgent:
    def __init__(self):
        self.db_client = None
        self.cdd_guidelines = self._load_cdd_guidelines()
        
    async def initialize(self):
        """Initialize the MongoDB client"""
        if not self.db_client:
            self.db_client = AsyncMongoDBClient.get_shared_client(
                settings.DOCDB_URI, 
                settings.DOCDB_DATABASE_NAME
            )
    
    def _load_cdd_guidelines(self) -> str:
        """Load and return CDD guidelines"""
        return """
        CDD FIELD NAMING & FORMATTING GUIDELINES:
        
        NAMING:
        - Use camelCase (e.g., entityIncorporationName, interestRateSpread)
        - Must be less than 64 characters
        - Use descriptive names reflecting content/purpose
        - Avoid acronyms unless widely used
        - Avoid abbreviations or overly technical terms
        - For boolean fields: prefix with "is", "has" (e.g., isActive, hasAccess)
        - For dates: include "Date" in name (e.g., amortizationStartDate, valueDate)
        - For amounts: include "amount", "payment", "price" (e.g., totalEquityAmount)
        - For rates: include "rate" in name (e.g., interestRate)
        
        DATA TYPES & DESCRIPTIONS:
        - STRING: Text, names, addresses, alphanumeric data. For enumerations with valid values.
        - DECIMAL: Rates, percentages, precise numeric values. For percentages: "Expressed in decimal format. For example, 10% is 0.1."
        - INTEGER: Whole numbers, counts, quantities. "Expressed as an integer in whole [units]"
        - DATE: Calendar dates. "Formatted as yyyy-mm-dd."
        - BOOLEAN: True/false values. "Valid values are TRUE or FALSE."
        - AMOUNT: Monetary values, prices, costs. "Expressed in [currency]."
        - TIMESTAMP: Time-based data (auto-generated). "YYYY-MM-DD hh:mm:ss.sss"
        
        DESCRIPTION REQUIREMENTS:
        - Clear, professional descriptions
        - Specify format requirements (decimal format, date format, etc.)
        - Include valid value ranges when applicable
        - For enumerations: include list of valid values in description
        """

    async def get_enriched_cdd_attributes(self) -> List[EnrichedCDDAttribute]:
        """Get all CDD attributes with enriched context information"""
        await self.initialize()
        
        # Get attributes from database
        attributes = await self.db_client.find_all("attributes")
        return [EnrichedCDDAttribute(**attr) for attr in attributes]

    async def create_cdd_context(self) -> str:
        """Create formatted context string with all CDD field names and descriptions"""
        attributes = await self.get_enriched_cdd_attributes()
        
        context_parts = []
        for attr in attributes:
            context_line = f"• {attr.name}"
            if attr.display_name and attr.display_name != attr.name:
                context_line += f" ({attr.display_name})"
            if attr.data_type:
                context_line += f" [{attr.data_type}]"
            if attr.category:
                context_line += f" [Category: {attr.category}]"
            if attr.description:
                # Truncate very long descriptions to keep context manageable
                desc_truncated = attr.description[:200] + "..." if len(attr.description) > 200 else attr.description
                context_line += f": {desc_truncated}"
            
            context_parts.append(context_line)
        
        return "\n".join(context_parts)

    async def find_best_cdd_matches(self, field_name: str, field_definition: str) -> List[CDDMatchResult]:
        """Use GPT-4 to find top 3 best matching CDD fields"""
        
        cdd_context = await self.create_cdd_context()
        
        prompt = f"""
        You are an expert in financial data mapping and ALM (Asset Liability Management) systems.
        
        Field to Match: {field_name}
        Field Definition: {field_definition}
        
        Available CDD Attributes:
        {cdd_context}
        
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
        ]
        """
        
        try:
            response = client.chat.completions.create(
                model=settings.MODEL_TO_USE,
                messages=[
                    {"role": "system", "content": "You are a financial data mapping expert specializing in ALM and banking systems. Provide only valid JSON response."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            matches_data = json.loads(result)
            
            # Get full attribute details for matches
            attributes = await self.get_enriched_cdd_attributes()
            attr_dict = {attr.name: attr for attr in attributes}
            
            matches = []
            for match in matches_data:
                if match["name"] in attr_dict:
                    attr = attr_dict[match["name"]]
                    matches.append(CDDMatchResult(
                        cdd_field=attr.name,
                        display_name=attr.display_name,
                        data_type=attr.data_type,
                        description=attr.description,
                        category=attr.category,
                        confidence_score=match["confidence_score"]
                    ))
            
            return matches
            
        except Exception as e:
            logger.error(f"Error finding CDD matches: {e}")
            return []

    async def create_new_cdd_field_suggestion(self, field_name: str, field_definition: str) -> Optional[NewCDDFieldSuggestion]:
        """Use GPT-4 to suggest a new CDD field based on field name and definition"""
        
        # Get categories for context
        categories = await self.db_client.find_all("categories")
        category_context = "\n".join([f"• {cat['name']}: {cat.get('description', '')}" for cat in categories])
        
        prompt = f"""
        You are an expert in financial data mapping and CDD (Common Data Dictionary) design.
        
        Field to Create: {field_name}
        Field Definition: {field_definition}
        
        Available CDD Categories:
        {category_context}
        
        CDD Guidelines:
        {self.cdd_guidelines}
        
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
        }}
        """
        
        try:
            response = client.chat.completions.create(
                model=settings.MODEL_TO_USE,
                messages=[
                    {"role": "system", "content": "You are a financial data expert specializing in CDD design. Provide only valid JSON response."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.2
            )
            
            result = response.choices[0].message.content.strip()
            suggestion_data = json.loads(result)
            
            return NewCDDFieldSuggestion(
                category=suggestion_data["category"],
                attribute=suggestion_data["attribute"],
                description=suggestion_data["description"],
                label=suggestion_data["label"],
                data_type=suggestion_data.get("data_type"),
                tag="ZM"
            )
            
        except Exception as e:
            logger.error(f"Error creating new field suggestion: {e}")
            return None

    async def process_field_mapping(self, request: FieldMappingRequest) -> FieldMappingResponse:
        """Process a single field mapping request"""
        
        # First, try to find matches
        matches = await self.find_best_cdd_matches(request.field_name, request.context_definition)
        
        # If no good matches found, suggest new field
        new_field_suggestion = None
        status = "matched"
        
        if not matches or (matches and matches[0].confidence_score < 0.6):
            new_field_suggestion = await self.create_new_cdd_field_suggestion(
                request.field_name, 
                request.context_definition
            )
            status = "new_suggestion" if new_field_suggestion else "no_match"
        
        return FieldMappingResponse(
            field_name=request.field_name,
            context_definition=request.context_definition,
            matches=matches,
            new_field_suggestion=new_field_suggestion,
            status=status
        )

# Global agent instance
_agent = None

def get_agent() -> CDDMappingAgent:
    """Get the global agent instance"""
    global _agent
    if _agent is None:
        _agent = CDDMappingAgent()
    return _agent

async def initialize_agent():
    """Initialize the global agent"""
    agent = get_agent()
    await agent.initialize()
    return agent 