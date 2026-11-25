from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.database.session import check_database

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI Agent Memory Forensics and Verified Recovery",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/")
def root():
    return {
        "project": "MemoryShield AI",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "service": "memoryshield-backend",
    }


@app.get("/api/ready")
def readiness():
    try:
        check_database()
        return {
            "status": "ready",
            "database": "connected",
        }
    except SQLAlchemyError:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )
