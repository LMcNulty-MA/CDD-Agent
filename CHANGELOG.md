# CDD-AI-Agent Changelog/Release Notes

### 2025-07-09
-----------------------------------------
#### What's New
 - Azure OpenAI integration with dynamic configuration management
 - Database-driven LLM endpoint configuration via Dynamic Config Manager
 - Added langchain-openai dependency for Azure deployment support

#### Breaking Changes / Removals
 - Replaced hardcoded OpenAI API with Azure OpenAI endpoints
 - Configuration now loaded dynamically from database instead of static settings

#### Bug fixes / Improvements
 - Removed all hardcoded OpenAI API key references
 - Updated CLI tool and web services to use Azure OpenAI exclusively
 - Removed unused agent.py file (system uses direct prompting, not agents with tools)
 - Optimized performance: uses global Azure OpenAI client singleton, no per-request initialization

### 2025-07-08
-----------------------------------------
#### What's New
 - Initial release of CDD Mapping Agent FastAPI application
 - Standardized field mapping format supporting both JSON and CSV input
 - MongoDB integration for enriched CDD attributes with category context
 - RESTful API endpoints for field mapping and database population
 - OpenAI-powered intelligent field matching and new field suggestions
 - Dark mode Swagger UI documentation
 - Bulk field mapping capabilities
 - File upload support for CSV and JSON formats
 - Standardized output format for recommendations

#### Features
 - **Field Mapping**: Map individual or bulk fields to existing CDD attributes
 - **New Field Suggestions**: AI-powered suggestions for new CDD fields when no matches found
 - **Database Population**: API endpoint to populate MongoDB with CDD data
 - **Export Capabilities**: Export recommendations in standardized CSV/JSON format
 - **File Upload**: Upload and process CSV or JSON files for bulk mapping
 - **Health Monitoring**: Health check endpoint with version information

#### Breaking Changes / Removals
 - Migrated from CLI-based tool to web API
 - Replaced CSV file storage with MongoDB database
 - Standardized input/output formats

#### Bug fixes / Improvements
 - Enhanced CDD context with category information
 - Improved matching accuracy with enriched attribute data
 - Better error handling and logging
 - Scalable architecture for organization-wide deployment 