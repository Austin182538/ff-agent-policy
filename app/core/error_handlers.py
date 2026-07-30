"""
Comprehensive error handling for the NFL Analytics API
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError, OperationalError
from pydantic import ValidationError
import logging
import traceback
from typing import Union
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('nfl_analytics.log', mode='a') if os.access('.', os.W_OK) else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)

def setup_error_handlers(app: FastAPI):
    """Setup all error handlers for the FastAPI application"""
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions"""
        logger.warning(f"HTTP {exc.status_code}: {exc.detail} - URL: {request.url}")
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "HTTP Error",
                "status_code": exc.status_code,
                "detail": exc.detail,
                "path": str(request.url.path),
                "method": request.method
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle request validation errors"""
        logger.warning(f"Validation error: {exc.errors()} - URL: {request.url}")
        
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation Error",
                "status_code": 422,
                "detail": "Request validation failed",
                "errors": exc.errors(),
                "path": str(request.url.path),
                "method": request.method
            }
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
        """Handle Pydantic validation errors"""
        logger.warning(f"Pydantic validation error: {exc.errors()} - URL: {request.url}")
        
        return JSONResponse(
            status_code=422,
            content={
                "error": "Data Validation Error",
                "status_code": 422,
                "detail": "Data validation failed",
                "errors": exc.errors(),
                "path": str(request.url.path),
                "method": request.method
            }
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        """Handle SQLAlchemy database errors"""
        logger.error(f"Database error: {str(exc)} - URL: {request.url}")
        
        # Different handling based on error type
        if isinstance(exc, DisconnectionError):
            status_code = 503
            detail = "Database connection lost. Please try again."
            error_type = "Database Connection Error"
        elif isinstance(exc, OperationalError):
            status_code = 503
            detail = "Database operation failed. Please try again."
            error_type = "Database Operation Error"
        else:
            status_code = 500
            detail = "A database error occurred. Please try again."
            error_type = "Database Error"
        
        return JSONResponse(
            status_code=status_code,
            content={
                "error": error_type,
                "status_code": status_code,
                "detail": detail,
                "path": str(request.url.path),
                "method": request.method,
                "suggestion": "If this persists, please check the database connection."
            }
        )

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError):
        """Handle missing key errors"""
        logger.error(f"Key error: {str(exc)} - URL: {request.url}")
        
        return JSONResponse(
            status_code=400,
            content={
                "error": "Missing Required Field",
                "status_code": 400,
                "detail": f"Required field '{str(exc)}' is missing or invalid",
                "path": str(request.url.path),
                "method": request.method
            }
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle value errors"""
        logger.error(f"Value error: {str(exc)} - URL: {request.url}")
        
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid Value",
                "status_code": 400,
                "detail": f"Invalid value provided: {str(exc)}",
                "path": str(request.url.path),
                "method": request.method
            }
        )

    @app.exception_handler(ImportError)
    async def import_error_handler(request: Request, exc: ImportError):
        """Handle import errors"""
        logger.error(f"Import error: {str(exc)} - URL: {request.url}")
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Service Unavailable",
                "status_code": 500,
                "detail": "A required service component is not available",
                "path": str(request.url.path),
                "method": request.method,
                "suggestion": "Please contact support if this persists."
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all other exceptions"""
        logger.error(f"Unexpected error: {str(exc)} - URL: {request.url}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Don't expose internal error details in production
        if os.getenv("ENVIRONMENT", "development") == "development":
            detail = str(exc)
            traceback_info = traceback.format_exc()
        else:
            detail = "An unexpected error occurred"
            traceback_info = None
        
        response_content = {
            "error": "Internal Server Error",
            "status_code": 500,
            "detail": detail,
            "path": str(request.url.path),
            "method": request.method,
            "suggestion": "Please try again or contact support if the issue persists."
        }
        
        if traceback_info:
            response_content["traceback"] = traceback_info
        
        return JSONResponse(
            status_code=500,
            content=response_content
        )

    logger.info("✅ Error handlers configured successfully")

def log_startup_info():
    """Log important startup information"""
    logger.info("🏈 NFL Analytics API Starting Up")
    logger.info(f"   Python version: {sys.version}")
    logger.info(f"   Working directory: {os.getcwd()}")
    logger.info(f"   Environment: {os.getenv('ENVIRONMENT', 'development')}")
    
def log_shutdown_info():
    """Log shutdown information"""
    logger.info("🛑 NFL Analytics API Shutting Down")

# Health check utilities
async def health_check() -> dict:
    """Comprehensive health check"""
    health_status = {
        "status": "healthy",
        "timestamp": "2024-12-01T00:00:00Z",  # Would use datetime.utcnow() in real implementation
        "version": "1.0.0",
        "checks": {}
    }
    
    # Database check
    try:
        from app.core.database import SessionLocal
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        health_status["checks"]["database"] = {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        health_status["checks"]["database"] = {"status": "unhealthy", "message": str(e)}
        health_status["status"] = "degraded"
    
    # Configuration check
    try:
        from app.core.config import settings
        health_status["checks"]["config"] = {"status": "healthy", "message": "Configuration loaded"}
    except Exception as e:
        health_status["checks"]["config"] = {"status": "unhealthy", "message": str(e)}
        health_status["status"] = "degraded"
    
    return health_status 