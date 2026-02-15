"""Main FastAPI application."""
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from starlette.middleware.sessions import SessionMiddleware

from agent.api.routes import router
from agent.core.config import settings

# Configure logging
logging.basicConfig(
    level=settings.log_level.upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Event Scraper API",
    description="Generalized event scraping using browser automation and LLM extraction",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get(settings.session_secret),
    session_cookie="session",
    https_only=settings.cookie_https_only,  # set true in prod if HTTPS-only
    same_site="lax",
)

# Include API routes (prefix so they don't collide with SPA routes)
app.include_router(router, prefix="/api", tags=["scraping"])

DIST_DIR = Path(__file__).resolve().parent / "dist"
ASSETS_DIR = DIST_DIR / "assets"
INDEX_FILE = DIST_DIR / "index.html"

# Serve hashed assets (e.g., /assets/xxx.js)
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# Serve other static files in dist (favicon, etc.)
if DIST_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(DIST_DIR)), name="static")

# SPA fallback: everything else returns index.html (except /api)
@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        # Let FastAPI return 404 for unknown API routes
        return {"detail": "Not Found"}
    return FileResponse(str(INDEX_FILE))

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("Starting Event Scraper API")
    logger.info(f"Server will run on {settings.host}:{settings.port}")

@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("Shutting down Event Scraper API")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level
    )
