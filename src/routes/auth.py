from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from .. import crud, models, schemas, database, security, i18n_config
from ..config import settings

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, email=form_data.username, password=form_data.password)
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

@router.get("/login")
async def get_login_page(request: Request):
    templates = i18n_config.get_jinja_env(locale=request.state.locale)
    return templates.TemplateResponse("login.html", {"request": request, "lang": request.state.locale})

@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    owner = crud.authenticate_owner(db, email=email, password=password)
    if not owner:
        templates = i18n_config.get_jinja_env(locale=request.state.locale)
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect email or password", "lang": request.state.locale})

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=access_token_expires.total_seconds())
    return response

@router.get("/signup")
async def get_signup_page(request: Request):
    templates = i18n_config.get_jinja_env(locale=request.state.locale)
    return templates.TemplateResponse("signup.html", {"request": request, "lang": request.state.locale})

@router.post("/signup")
async def signup(request: Request, name: str = Form(...), email: str = Form(...), business_name: str = Form(...), slug: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    db_owner = crud.get_owner_by_email(db, email=email)
    if db_owner:
        templates = i18n_config.get_jinja_env(locale=request.state.locale)
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Email already registered", "lang": request.state.locale})
    db_owner = crud.get_owner_by_slug(db, slug=slug)
    if db_owner:
        templates = i18n_config.get_jinja_env(locale=request.state.locale)
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Business URL already taken", "lang": request.state.locale})

    owner_data = schemas.OwnerCreate(name=name, email=email, business_name=business_name, slug=slug, password=password)
    crud.create_owner(db=db, owner=owner_data)
    return RedirectResponse(url="/auth/login?signup_success=true", status_code=status.HTTP_302_FOUND)

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

async def get_current_owner(request: Request, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.cookies.get("access_token")
    if not token:
        raise credentials_exception
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

@router.get("/profile")
async def get_owner_profile(request: Request, current_owner: models.Owner = Depends(get_current_owner)):
    templates = i18n_config.get_jinja_env(locale=request.state.locale)
    return templates.TemplateResponse(
        "owner_profile.html", 
        {"request": request, "owner": current_owner, "lang": request.state.locale}
    )

@router.post("/profile")
async def update_owner_profile(
    request: Request,
    name: str = Form(...),
    business_name: str = Form(...),
    phone: Optional[str] = Form(None),
    current_owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    owner_update_data = schemas.OwnerProfileUpdate(
        name=name,
        business_name=business_name,
        phone=phone if phone else None # Ensure empty string becomes None
    )
    
    updated_owner = crud.update_owner_profile(db, current_owner, owner_update_data)
    
    templates = i18n_config.get_jinja_env(locale=request.state.locale)
    return templates.TemplateResponse(
        "owner_profile.html", 
        {"request": request, "owner": updated_owner, "lang": request.state.locale, "message": _("Profile updated successfully!")}
    )