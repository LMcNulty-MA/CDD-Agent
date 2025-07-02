import logging
from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import List, Dict, Any
from app.core.models import (
    DatabasePopulationRequest,
    DatabasePopulationResponse,
    EnrichedCDDAttribute,
    CDDCategory
)
from app.core.documentdb import AsyncMongoDBClient
from app.core.security import oauth2_scheme
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/populate-database",
    summary="Populate CDD Database",
    description="Populate the MongoDB database with CDD attributes, categories, and category-attribute mappings",
    response_model=DatabasePopulationResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(oauth2_scheme)]
)
async def populate_database(request: DatabasePopulationRequest, auth_request: Request):
    """Populate the CDD database with attributes, categories, and mappings"""
    try:
        # Initialize database client
        db_client = AsyncMongoDBClient.get_shared_client(
            settings.DOCDB_URI, 
            settings.DOCDB_DATABASE_NAME
        )
        
        # Process and enrich attributes with category information
        enriched_attributes = []
        
        # Create lookup dictionaries for enrichment
        categories_dict = {cat['name']: cat for cat in request.categories_data}
        category_attrs_dict = {}
        for ca in request.category_attributes_data:
            key = f"{ca['categoryName']}_{ca['attributeName']}"
            category_attrs_dict[key] = ca
        
        # Enrich attributes
        for attr in request.attributes_data:
            enriched_attr = attr.copy()
            
            # Find category information for this attribute
            for ca in request.category_attributes_data:
                if ca['attributeName'] == attr['name']:
                    category_name = ca['categoryName']
                    enriched_attr['category'] = category_name
                    
                    # Add category description
                    if category_name in categories_dict:
                        enriched_attr['category_description'] = categories_dict[category_name].get('description')
                    
                    # Add category-attribute specific information
                    enriched_attr.update({
                        'is_internal': ca.get('isInternal'),
                        'input_partition_order': ca.get('inputPartitionOrder'),
                        'output_partition_order': ca.get('outputPartitionOrder'),
                        'order': ca.get('order'),
                        'products': ca.get('products'),
                        'ma_internal': ca.get('maInternal')
                    })
                    break
            
            enriched_attributes.append(enriched_attr)
        
        # Clear existing collections and populate new data
        await db_client.drop_collection("attributes")
        await db_client.drop_collection("categories")
        await db_client.drop_collection("category_attributes")
        
        # Insert enriched attributes
        if enriched_attributes:
            await db_client.insert_documents("attributes", enriched_attributes)
            await db_client.create_index("attributes", "name", unique=True)
        
        # Insert categories
        if request.categories_data:
            await db_client.insert_documents("categories", request.categories_data)
            await db_client.create_index("categories", "name", unique=True)
        
        # Insert category-attribute mappings
        if request.category_attributes_data:
            await db_client.insert_documents("category_attributes", request.category_attributes_data)
            await db_client.create_index("category_attributes", "categoryName")
            await db_client.create_index("category_attributes", "attributeName")
        
        logger.info(f"Database populated successfully: {len(enriched_attributes)} attributes, {len(request.categories_data)} categories, {len(request.category_attributes_data)} mappings")
        
        return DatabasePopulationResponse(
            status="success",
            attributes_count=len(enriched_attributes),
            categories_count=len(request.categories_data),
            category_attributes_count=len(request.category_attributes_data),
            message="Database populated successfully with enriched CDD data"
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (like auth errors) as-is
        raise
    except Exception as e:
        logger.error(f"Error populating database: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to populate database. The database service may be temporarily unavailable. Please check your data format and try again later."
        )

@router.get(
    "/attributes",
    summary="Get All CDD Attributes",
    description="Get all CDD attributes with enriched context information",
    response_model=List[EnrichedCDDAttribute],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(oauth2_scheme)]
)
async def get_attributes(auth_request: Request):
    """Get all CDD attributes with enriched context"""
    try:
        # Initialize database client
        db_client = AsyncMongoDBClient.get_shared_client(
            settings.DOCDB_URI, 
            settings.DOCDB_DATABASE_NAME
        )
        
        # Get all attributes
        attributes = await db_client.find_all("attributes", projection={"_id": 0})
        
        logger.info(f"Retrieved {len(attributes)} CDD attributes")
        
        # Convert camelCase fields from database to snake_case for Pydantic models
        converted_attributes = []
        for attr in attributes:
            converted_attr = {
                'name': attr.get('name', ''),  # Provide default empty string
                'display_name': attr.get('displayName'),  # camelCase to snake_case
                'data_type': attr.get('dataType'),  # camelCase to snake_case
                'description': attr.get('description'),
                'tenant': attr.get('tenant'),
                'enum_type': attr.get('enumType'),  # camelCase to snake_case
                'category': attr.get('category'),
                'category_description': attr.get('category_description'),
                'is_internal': attr.get('is_internal'),
                'input_partition_order': attr.get('input_partition_order'),
                'output_partition_order': attr.get('output_partition_order'),
                'order': attr.get('order'),
                'products': attr.get('products'),
                'ma_internal': attr.get('ma_internal')
            }
            converted_attributes.append(EnrichedCDDAttribute(**converted_attr))
        
        return converted_attributes
        
    except HTTPException:
        # Re-raise HTTP exceptions (like auth errors) as-is
        raise
    except Exception as e:
        logger.error(f"Error retrieving attributes: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve CDD attributes. The database service may be temporarily unavailable. Please try again later."
        )

@router.get(
    "/categories",
    summary="Get All CDD Categories",
    description="Get all CDD categories",
    response_model=List[CDDCategory],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(oauth2_scheme)]
)
async def get_categories(auth_request: Request):
    """Get all CDD categories"""
    try:
        # Initialize database client
        db_client = AsyncMongoDBClient.get_shared_client(
            settings.DOCDB_URI, 
            settings.DOCDB_DATABASE_NAME
        )
        
        # Get all categories
        categories = await db_client.find_all("categories", projection={"_id": 0})
        
        logger.info(f"Retrieved {len(categories)} CDD categories")
        
        # Convert camelCase fields from database to snake_case for Pydantic models
        converted_categories = []
        for cat in categories:
            converted_cat = {
                'name': cat.get('name', ''),  # Provide default empty string
                'display_name': cat.get('displayName'),  # camelCase to snake_case
                'description': cat.get('description'),
                'tenant': cat.get('tenant')
            }
            converted_categories.append(CDDCategory(**converted_cat))
        
        return converted_categories
        
    except HTTPException:
        # Re-raise HTTP exceptions (like auth errors) as-is
        raise
    except Exception as e:
        logger.error(f"Error retrieving categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve CDD categories. The database service may be temporarily unavailable. Please try again later."
        ) 