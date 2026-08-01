from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import json
import gettext
import os
import logging

from . import models, schemas, crud, security, notifications
from .database import SessionLocal, engine, Base, get_db
from .config import settings
from .i18n_config import get_jinja_env

app = FastAPI()

# Create database tables on startup
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

# Dependency for getting the Jinja2 environment with i18n
def get_jinja_env_dependency(request: Request):
    locale = request.cookies.get("lang", "en")
    return get_jinja_env(locale)

@app.get("/health", response_class=HTMLResponse)
async def health():
    return {"status": "ok"}

# Placeholder for owner signup
@app.post("/owner/signup", response_model=schemas.Token)
async def signup_owner(owner: schemas.OwnerCreate, db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=owner.email)
    if db_owner:
        raise HTTPException(status_code=400, detail="Email already registered")
    # Generate a slug if not provided, or sanitize it
    if not owner.slug:
        owner.slug = owner.business_name.lower().replace(" ", "-")
    db_owner = crud.create_owner(db=db, owner=owner)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": db_owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "owner": schemas.Owner.from_orm(db_owner)}
