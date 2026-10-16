from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from . import database, models, config

import bcrypt
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')
    try:
        return bcrypt.checkpw(plain_password[:72], hashed_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    if isinstance(password, str):
        password = password.encode('utf-8')
    return bcrypt.hashpw(password[:72], bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=config.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.settings.SECRET_KEY, algorithm=config.settings.ALGORITHM)
    return encoded_jwt

from fastapi import Request

oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

async def get_current_owner(request: Optional[Any] = None, token: Optional[str] = Depends(oauth2_scheme_optional), db: Session = Depends(database.get_db)) -> models.Owner:
    if isinstance(request, str):
        actual_token = request
        actual_db = token if token is not None and not isinstance(token, str) else db
        actual_request = None
    else:
        actual_request = request
        actual_token = token or (actual_request.cookies.get("access_token") if actual_request and hasattr(actual_request, "cookies") else None)
        actual_db = db

    if not actual_token:
        if actual_request and hasattr(actual_request, "headers") and ("text/html" in actual_request.headers.get("accept", "") or "/owner" in str(getattr(actual_request.url, "path", "")) or "/dashboard" in str(getattr(actual_request.url, "path", ""))):
            raise HTTPException(status_code=302, detail="Redirect to login", headers={"Location": "/login"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(actual_token, config.settings.SECRET_KEY, algorithms=[config.settings.ALGORITHM])
        sub: str = payload.get("sub")
        if sub is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    if actual_db is None:
        raise credentials_exception

    from . import crud
    if str(sub).isdigit():
        owner = crud.get_owner(actual_db, owner_id=int(sub))
    else:
        owner = crud.get_owner_by_email(actual_db, email=sub)

    if owner is None:
        raise credentials_exception
    return owner

def authenticate_owner(db: Session, email_or_username: str, password: str, client_ip: Optional[str] = None):
    from . import crud
    return crud.authenticate_owner(db, email=email_or_username, password=password)

def authenticate_customer(db: Session, email: str, password: str, client_ip: Optional[str] = None):
    customer = db.query(models.Customer).filter(models.Customer.email == email).first()
    if not customer:
        return False
    if not customer.hashed_password or not verify_password(password, customer.hashed_password):
        return False
    return customer

def decode_access_token(token: str):
    return jwt.decode(token, config.settings.SECRET_KEY, algorithms=[config.settings.ALGORITHM])

