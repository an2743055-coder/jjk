"""
Yeager AI — FastAPI Backend
Handles project enquiry and demo booking form submissions, storing them in MongoDB.

Local dev:
    uvicorn main:app --reload --port 8000

Render: set environment variables directly in the Render dashboard.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import motor.motor_asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
import os

# Load .env (only matters locally; Render injects env vars directly)
load_dotenv()

MONGODB_URI          = os.getenv("MONGODB_URI", "")
DB_NAME              = os.getenv("DB_NAME", "yeager")
COLLECTION_NAME      = os.getenv("COLLECTION_NAME", "project_enquiries")
DEMO_COLLECTION_NAME = os.getenv("DEMO_COLLECTION_NAME", "demo_bookings")

# Directory where this file lives — works on both local and Render
BASE_DIR = Path(__file__).parent


# ============================================================
# Pydantic models
# ============================================================

class ProjectEnquiry(BaseModel):
    name: str               = Field(..., min_length=1,  max_length=100)
    email: EmailStr
    company: Optional[str]  = Field(None, max_length=200)
    project_type: str       = Field(..., min_length=1,  max_length=100)
    project_description: str= Field(..., min_length=20, max_length=5000)
    budget: Optional[str]   = Field(None, max_length=100)
    timeline: Optional[str] = Field(None, max_length=100)


class EnquiryResponse(BaseModel):
    success: bool
    message: str
    id: str


class DemoBooking(BaseModel):
    name: str             = Field(..., min_length=1, max_length=100)
    email: EmailStr
    company: str          = Field(..., min_length=1, max_length=200)
    volume: Optional[str] = Field(None, max_length=100)
    interest: Optional[str] = Field(None, max_length=5000)


class DemoBookingResponse(BaseModel):
    success: bool
    message: str
    id: str


# ============================================================
# Database
# ============================================================

db_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None


def get_collection():
    if db_client is None:
        raise RuntimeError("Database not connected")
    return db_client[DB_NAME][COLLECTION_NAME]


def get_demo_collection():
    if db_client is None:
        raise RuntimeError("Database not connected")
    return db_client[DB_NAME][DEMO_COLLECTION_NAME]


# ============================================================
# App lifecycle
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_client

    if not MONGODB_URI or "<username>" in MONGODB_URI or "<password>" in MONGODB_URI:
        print("⚠️  MONGODB_URI not configured — submissions will fail until you set it.")
    else:
        try:
            db_client = motor.motor_asyncio.AsyncIOMotorClient(
                MONGODB_URI,
                tls=True,
                tlsAllowInvalidCertificates=True,
            )
            await db_client.admin.command("ping")
            print(f"✅ MongoDB connected → {DB_NAME}.{COLLECTION_NAME}")
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            db_client = None

    yield

    if db_client:
        db_client.close()
        print("🔌 MongoDB disconnected")


# ============================================================
# App
# ============================================================

app = FastAPI(
    title="Yeager AI API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Routes
# ============================================================

@app.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_frontend():
    """Serve the main HTML page."""
    return FileResponse(BASE_DIR / "index.html")


@app.get("/health")
async def health():
    return {
        "status": "ok" if db_client else "degraded",
        "database": "connected" if db_client else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/submit", response_model=EnquiryResponse, status_code=201)
async def submit_project(enquiry: ProjectEnquiry):
    """Save a project enquiry to MongoDB."""
    if db_client is None:
        raise HTTPException(
            status_code=503,
            detail="Database not connected. Please configure MONGODB_URI.",
        )

    doc = {
        **enquiry.model_dump(),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "status": "new",
    }

    try:
        result = await get_collection().insert_one(doc)
        inserted_id = str(result.inserted_id)
        print(f"📥 New enquiry → {enquiry.name} <{enquiry.email}> [{enquiry.project_type}] ID:{inserted_id}")
        return EnquiryResponse(
            success=True,
            message="Project submitted! We'll be in touch within 24 hours.",
            id=inserted_id,
        )
    except Exception as e:
        print(f"❌ Insert failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to save. Please try again.")


@app.get("/api/enquiries")
async def list_enquiries(limit: int = 50):
    """List recent project enquiries (add auth before making this public)."""
    if db_client is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    cursor = get_collection().find({}, {"_id": 0}).sort("submitted_at", -1).limit(limit)
    results = await cursor.to_list(length=limit)
    return {"count": len(results), "enquiries": results}


@app.post("/api/book-demo", response_model=DemoBookingResponse, status_code=201)
async def book_demo(booking: DemoBooking):
    """Save a demo booking to MongoDB."""
    if db_client is None:
        raise HTTPException(
            status_code=503,
            detail="Database not connected. Please configure MONGODB_URI.",
        )

    doc = {
        **booking.model_dump(),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "status": "new",
    }

    try:
        result = await get_demo_collection().insert_one(doc)
        inserted_id = str(result.inserted_id)
        print(f"📅 Demo booked → {booking.name} <{booking.email}> [{booking.company}] ID:{inserted_id}")
        return DemoBookingResponse(
            success=True,
            message="Demo booked! We'll be in touch within 4 business hours.",
            id=inserted_id,
        )
    except Exception as e:
        print(f"❌ Demo insert failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to save. Please try again.")


@app.get("/api/demos")
async def list_demos(limit: int = 50):
    """List recent demo bookings (add auth before making this public)."""
    if db_client is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    cursor = get_demo_collection().find({}, {"_id": 0}).sort("submitted_at", -1).limit(limit)
    results = await cursor.to_list(length=limit)
    return {"count": len(results), "demos": results}
