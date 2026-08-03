from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .database import get_db, create_tables
from .i18n_config import get_jinja_templates
from .config import settings
import logging

app = FastAPI()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default templates for root/health, actual endpoints would use a dependency
templates = get_jinja_templates('en') 

@app.on_event("startup")
def on_startup():
    create_tables()
    logger.info("Database tables created.")
    if settings.TESTING:
        logger.info("Application is running in TESTING mode.")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # Placeholder for the main landing page
    return templates.TemplateResponse("root.html", {"request": request, "message": "Welcome to BookSlot!"})

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Placeholder for other routes like owner signup, login, dashboard, booking page etc.
# These would be implemented based on the completed steps.