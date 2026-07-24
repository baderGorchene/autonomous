from fastapi import APIRouter, Request, Depends, Form, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta
import logging

from .. import crud, schemas, security, database, models
from ..config import settings

router = APIRouter()

logger = logging.getLogger(__name__)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
    
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=access_token_expires.total_seconds())
    return response

@router.get("/logout")
def logout(response: Response):
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response

@router.get("/signup")
def signup_form(request: Request):
    return request.state.templates.TemplateResponse("signup.html", {"request": request, "lang": request.state.locale})

@router.post("/signup")
async def signup(request: Request, name: str = Form(...), business_name: str = Form(...), slug: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        error_message = request.state.templates.env.gettext("Email already registered")
        return request.state.templates.TemplateResponse("signup.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)
    
    owner = crud.get_owner_by_slug(db, slug=slug)
    if owner:
        error_message = request.state.templates.env.gettext("Business slug already taken")
        return request.state.templates.TemplateResponse("signup.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)

    try:
        owner_create = schemas.OwnerCreate(name=name, business_name=business_name, slug=slug, email=email, password=password)
        db_owner = crud.create_owner(db=db, owner=owner_create)
        
        return RedirectResponse(url="/auth/login?signup_success=true", status_code=303)
    except ValidationError as e:
        logger.error(f"Validation error during owner signup: {e.errors()}")
        error_message = request.state.templates.env.gettext(f"Invalid input for signup: {e.errors()}")
        return request.state.templates.TemplateResponse("signup.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)
    except SQLAlchemyError as e:
        logger.exception(f"Database error during owner signup: {e}")
        db.rollback()
        error_message = request.state.templates.env.gettext("A database error occurred during signup. Please try again.")
        return request.state.templates.TemplateResponse("signup.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)
    except Exception as e:
        logger.exception(f"Unexpected error during owner signup: {e}")
        error_message = request.state.templates.env.gettext("An unexpected error occurred during signup. Please try again.")
        return request.state.templates.TemplateResponse("signup.html", {"request": request, "error_message": error_message, "lang": request.state.locale}, status_code=400)
