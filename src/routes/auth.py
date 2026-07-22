from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from .. import crud, schemas, security, database
from ..config import settings

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

async def get_current_owner(request: Request, db: Session = Depends(get_db)) -> schemas.Owner:
    token = request.cookies.get("access_token") # Assuming token is stored in a cookie
    if not token:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": "/auth/login"}
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token_data = security.verify_access_token(token, credentials_exception)
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

@router.get("/login")
async def login_page(request: Request):
    # This should return a login.html template
    # For now, let's just return a placeholder.
    # The actual login page template is not provided in CURRENT FILES.
    # I'll create a minimal one.
    return request.state.templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def owner_login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        # Re-render login page with error
        return request.state.templates.TemplateResponse("login.html", {
            "request": request,
            "error_message": "Invalid email or password",
            "lang": request.state.locale
        })
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires)
    return response

@router.post("/logout")
async def owner_logout(response: Response):
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response

@router.get("/signup")
async def signup_page(request: Request):
    # This should return a signup.html template
    # For now, let's just return a placeholder.
    # The actual signup page template is not provided in CURRENT FILES.
    # I'll create a minimal one.
    return request.state.templates.TemplateResponse("signup.html", {"request": request})

@router.post("/signup")
async def owner_signup(
    request: Request,
    response: Response,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    db: Session = Depends(get_db)
):
    existing_owner = crud.get_owner_by_email(db, email=email)
    if existing_owner:
        return request.state.templates.TemplateResponse("signup.html", {
            "request": request,
            "error_message": "Email already registered",
            "lang": request.state.locale
        })
    
    existing_slug_owner = crud.get_owner_by_slug(db, slug=slug)
    if existing_slug_owner:
        return request.state.templates.TemplateResponse("signup.html", {
            "request": request,
            "error_message": "Business URL (slug) already taken",
            "lang": request.state.locale
        })

    owner_create = schemas.OwnerCreate(
        name=name,
        email=email,
        password=password,
        business_name=business_name,
        slug=slug
    )
    owner = crud.create_owner(db, owner_create)

    # Log in the new owner immediately
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires)
    return response
