from fastapi import APIRouter, Depends, HTTPException, status, Form, Request, Response
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta
from src import crud, schemas, security, database, models
from src.config import settings
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import os

router = APIRouter()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("bookslot_access_token")
    if not token:
        token = request.headers.get("Authorization")
        if token and token.startswith("Bearer "):
            token = token.split(" ")[1]
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    payload = security.decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    owner = crud.get_owner_by_email(db, email=email)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Owner not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return owner

@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(request: Request, response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="bookslot_access_token", 
        value=access_token, 
        httponly=True, 
        max_age=access_token_expires.total_seconds(), 
        expires=access_token_expires.total_seconds()
    )
    return response

@router.get("/signup", response_class=HTMLResponse)
async def get_signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@router.post("/signup")
async def signup(request: Request, response: Response, 
                 name: str = Form(...), 
                 email: str = Form(...), 
                 password: str = Form(...), 
                 business_name: str = Form(...), 
                 slug: str = Form(...), 
                 db: Session = Depends(get_db)):
    
    if crud.get_owner_by_email(db, email):
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Email already registered"})
    if crud.get_owner_by_slug(db, slug):
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Business URL already taken"})

    owner_create = schemas.OwnerCreate(name=name, email=email, password=password, business_name=business_name, slug=slug)
    owner = crud.create_owner(db, owner_create)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="bookslot_access_token", 
        value=access_token, 
        httponly=True, 
        max_age=access_token_expires.total_seconds(), 
        expires=access_token_expires.total_seconds()
    )
    return response

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("bookslot_access_token")
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
