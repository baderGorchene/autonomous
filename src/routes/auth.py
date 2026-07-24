from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional

from .. import crud, schemas, security, models, database
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

async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"},
            detail="Not authenticated, redirecting to login",
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except Exception:
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner

@router.get("/signup")
async def signup_page(request: Request):
    return request.state.templates.TemplateResponse("signup.html", {"request": request, "lang": request.state.locale})

@router.post("/signup")
async def signup_owner(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return request.state.templates.TemplateResponse("signup.html", {
            "request": request,
            "error_message": request.state.templates.env.gettext("Email already registered"),
            "name": name, "email": email, "business_name": business_name, "slug": slug,
            "lang": request.state.locale
        })
    owner = crud.get_owner_by_slug(db, slug=slug)
    if owner:
        return request.state.templates.TemplateResponse("signup.html", {
            "request": request,
            "error_message": request.state.templates.env.gettext("Business URL already taken"),
            "name": name, "email": email, "business_name": business_name, "slug": slug,
            "lang": request.state.locale
        })

    try:
        owner_schema = schemas.OwnerCreate(
            name=name, email=email, password=password, business_name=business_name, slug=slug
        )
        crud.create_owner(db=db, owner=owner_schema)
        response = Response(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/auth/login"})
        return response
    except Exception as e:
        return request.state.templates.TemplateResponse("signup.html", {
            "request": request,
            "error_message": request.state.templates.env.gettext(f"An error occurred during signup: {e}"),
            "name": name, "email": email, "business_name": business_name, "slug": slug,
            "lang": request.state.locale
        })

@router.get("/login")
async def login_page(request: Request, error_message: Optional[str] = None):
    return request.state.templates.TemplateResponse("login.html", {"request": request, "error_message": error_message, "lang": request.state.locale})

@router.post("/login")
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    owner = crud.authenticate_owner(db, email, password)
    if not owner:
        return request.state.templates.TemplateResponse("login.html", {
            "request": request,
            "error_message": request.state.templates.env.gettext("Incorrect email or password"),
            "email": email,
            "lang": request.state.locale
        })
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    
    response = Response(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/dashboard"})
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=access_token_expires.total_seconds())
    return response

@router.post("/logout")
async def logout(response: Response):
    response = Response(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/auth/login"})
    response.delete_cookie(key="access_token")
    return response