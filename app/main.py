import uvicorn
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

# In house imports
from requests.exceptions import HTTPError
from app.config import settings
from app.core import exceptions
from app.routers import health, cdd_mapping, web_interface
from app.logging_config import configure_logging
from app.swagger_html import custom_swagger_ui_html

configure_logging()

api_context = 'cdd-agent'


def get_application() -> FastAPI:
    """ Creates and configures a FastAPI application instance with dark mode support. """

    application: FastAPI = FastAPI(
        title='CDD Mapping Agent API',
        description='CDD Mapping Agent API with Dark Mode Support',
        version='V1',
        openapi_url=f'/{api_context}/openapi.json',
        docs_url=None,  # Disable default docs to use custom dark mode version
        redoc_url=f'/{api_context}/redoc'
    )
    
    application.add_middleware(GZipMiddleware)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(cdd_mapping.router, prefix=f'/{api_context}')
    application.include_router(health.router, prefix=f'/{api_context}')
    application.include_router(web_interface.router, prefix=f'/{api_context}/web')

    # Exception handlers - properly return JSONResponse objects
    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, 'headers', None)
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation error", "errors": exc.errors()}
        )

    @application.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logging.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

    # Custom Swagger UI with dark theme support
    @application.get(f"/{api_context}/docs", include_in_schema=False)
    async def custom_swagger_docs():
        """Custom Swagger UI endpoint with dark mode toggle functionality."""
        return HTMLResponse(custom_swagger_ui_html())

    print(f'CDD Mapping Agent is up and running with dark mode support!')

    return application


app = get_application()

# Main method to run the application on http://localhost:5000/cdd-agent/
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=5000, log_level="info", reload=True) 