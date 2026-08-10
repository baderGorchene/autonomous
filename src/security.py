from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models, schemas
from .config import settings
import gettext
_ = gettext.gettext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

# --- Owner Security ---
def create_owner_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "owner"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def get_owner_from_token(db: Session, token: str, credentials_exception: HTTPException):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        if email is None or token_type != "owner":
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    owner = db.query(models.Owner).filter(models.Owner.email == token_data.email).first()
    if owner is None:
        raise credentials_exception
    return owner

def authenticate_owner(db: Session, email: str, password: str):
    owner = db.query(models.Owner).filter(models.Owner.email == email).first()
    if not owner:
        return False
    if not verify_password(password, owner.hashed_password):
        return False
    return owner

def get_current_owner(db: Session, token: str, credentials_exception: HTTPException):
    return get_owner_from_token(db, token, credentials_exception)

# --- Customer Security ---
def create_customer_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "customer"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def get_customer_from_token(db: Session, token: str, credentials_exception: HTTPException):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        if email is None or token_type != "customer":
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    customer = db.query(models.Customer).filter(models.Customer.email == token_data.email).first()
    if customer is None:
        raise credentials_exception
    return customer

def authenticate_customer(db: Session, email: str, password: str):
    customer = db.query(models.Customer).filter(models.Customer.email == email).first()
    if not customer:
        return False
    if not verify_password(password, customer.hashed_password):
        return False
    return customer

def get_current_customer(db: Session, token: str, credentials_exception: HTTPException):
    return get_customer_from_token(db, token, credentials_exception)
