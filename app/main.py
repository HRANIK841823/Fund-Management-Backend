from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, init_db
from app.models import FundSettings
from app.routers import admin, auth, member


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # create tables + seed default settings on startup
    yield


app = FastAPI(
    title="Fund Management & Monthly Payment Tracker",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS only for the configured frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(member.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    fund = db.get(FundSettings, 1)
    return {
        "status": "ok",
        "monthly_contribution_amount": fund.monthly_contribution_amount if fund else None,
    }
