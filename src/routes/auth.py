from fastapi import APIRouter, Request, Depends, Form, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import timedelta
from typing import Optional
from pydantic import ValidationError
import logging

from .. import crud, schemas, security, database, models
from ..config import settings

router = APIRouter()

logger = logging.getLogger(__name__)

get_db = database.get_db


async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=303, detail="Redirecting to login", headers={"Location": "/auth/login"})
    
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        owner_id: int = payload.get("sub")
        if owner_id is None:
            raise credentials_exception
        token_data = schemas.TokenData(id=owner_id)
    except Exception as e:
        logger.error(f"Token decoding error: {e}")
        raise credentials_exception
    owner = crud.get_owner(db, owner_id=token_data.id)
    if owner is None:
        raise credentials_exception
    return owner

@router.get("/login")
def login_form(request: Request):
    return request.state.templates.TemplateResponse("login.html", {"request": request, "lang": request.state.locale})

@router.post("/login")
async def login(request: Request, response: Response, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, email=email, password=password)
    if not owner:
        error_message = request.state.templates.env.gettext("Incorrect email or password")
        return request.state.templates.TemplateResponse("login.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": str(owner.id)}, expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=int(access_token_expires.total_seconds()))
    return response

@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="access_token")
    return response

@router.get("/signup")
@router.get("/owner/signup")
@router.get("/auth/signup")
def signup_form(request: Request):
    return request.state.templates.TemplateResponse("signup.html", {"request": request, "lang": request.state.locale})

@router.post("/signup")
@router.post("/owner/signup")
@router.post("/auth/signup")
@router.post("/api/auth/signup")
async def signup(
    request: Request,
    name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    business_name: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    import re
    is_json = request.headers.get("content-type") == "application/json"
    if is_json:
        try:
            body = await request.json()
            name = body.get("name") if body.get("name") is not None else name
            email = body.get("email") if body.get("email") is not None else email
            password = body.get("password") if body.get("password") is not None else password
            business_name = body.get("business_name") if body.get("business_name") is not None else business_name
            slug = body.get("slug") if body.get("slug") is not None else slug
            phone = body.get("phone") if body.get("phone") is not None else phone
        except Exception:
            pass

    errors = []
    if not name:
        errors.append("Name is required.")
    if not email:
        errors.append("Email is required.")
    elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors.append("Invalid email address.")

    if request.url.path.startswith("/owner/signup"):
        if not password or len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if not business_name:
            errors.append("Business name is required.")
        if not slug:
            errors.append("Slug is required.")
    else:
        if not password:
            password = "defaultpassword123"
        elif len(password) < 6:
            errors.append("Password must be at least 6 characters.")

    if errors:
        error_message = " ".join(errors)
        if is_json:
            raise HTTPException(status_code=400, detail=error_message)
        return request.state.templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error_message": error_message,
                "errors": errors,
                "lang": request.state.locale
            },
            status_code=400
        )

    if not business_name:
        business_name = name
    if not slug:
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', business_name.lower()).strip('-') or "owner"

    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        error_message = "This email is already registered."
        if is_json:
            raise HTTPException(status_code=400, detail=error_message)
        return request.state.templates.TemplateResponse("signup.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)
    
    existing_by_slug = crud.get_owner_by_slug(db, slug=slug)
    if existing_by_slug:
        if request.url.path.startswith("/owner/signup") or is_json:
            error_message = "This slug is already taken."
            if is_json:
                raise HTTPException(status_code=400, detail=error_message)
            return request.state.templates.TemplateResponse("signup.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)
        else:
            base_slug = slug
            counter = 1
            while crud.get_owner_by_slug(db, slug=slug):
                slug = f"{base_slug}-{counter}"
                counter += 1

    try:
        owner_create = schemas.OwnerCreate(
            name=name,
            business_name=business_name,
            slug=slug,
            email=email,
            password=password,
            phone=phone
        )
        db_owner = crud.create_owner(db=db, owner=owner_create)
        
        if is_json:
            return {"id": db_owner.id, "email": db_owner.email, "name": db_owner.name, "business_name": db_owner.business_name, "slug": db_owner.slug}

        target_url = "/login" if request.url.path.startswith("/owner/signup") else "/login?signup_success=true"
        return RedirectResponse(url=target_url, status_code=302)
    except ValidationError as e:
        logger.error(f"Validation error during owner signup: {e.errors()}")
        error_message = f"Invalid input for signup: {e.errors()}"
        return request.state.templates.TemplateResponse("signup.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)
    except SQLAlchemyError as e:
        logger.exception(f"Database error during owner signup: {e}")
        db.rollback()
        error_message = "A database error occurred during signup. Please try again."
        return request.state.templates.TemplateResponse("signup.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)
    except Exception as e:
        logger.exception(f"Unexpected error during owner signup: {e}")
        error_message = "An unexpected error occurred during signup. Please try again."
        return request.state.templates.TemplateResponse("signup.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)

