"""Health check endpoint."""
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint.
    
    Returns:
        Simple health status
    """
    return {"status": "healthy", "message": "QSScope backend is running"}
