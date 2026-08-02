from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from . import models, schemas, crud, security, notifications
from .database import engine, get_db, create_tables
from .config import settings
from .i18n_config import get_jinja_env
from typing import Annotated
from datetime import datetime, timedelta
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables on startup
create_tables()

app = FastAPI()

# Mount static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Dependency to get current owner
async def get_current_owner(db: Session = Depends(get_db), token: str = Depends(security.oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        owner_id: int = payload.get("sub")
        if owner_id is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    owner = crud.get_owner(db, owner_id=owner_id)
    if owner is None:
        raise credentials_exception
    return owner

@app.get("/health", response_class=HTMLResponse)
async def health_check():
    return "<h1>BookSlot Health Check: OK</h1>"

# Placeholder for the root endpoint, redirects to login for now
@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/owner/login", status_code=status.HTTP_302_FOUND)

# Placeholder for owner login
@app.get("/owner/login", response_class=HTMLResponse)
async def owner_login_page(request: Request):
    env = get_jinja_env(locale='en') # Default to English for login page for now
    templates = Jinja2Templates(env=env)
    return templates.TemplateResponse("owner_login.html", {"request": request})

# Placeholder for owner dashboard
@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, current_owner: Annotated[models.Owner, Depends(get_current_owner)]):
    # This will eventually render the dashboard with bookings
    env = get_jinja_env(locale='en') # Default to English for dashboard
    templates = Jinja2Templates(env=env)
    return templates.TemplateResponse("dashboard.html", {"request": request, "owner": current_owner})
