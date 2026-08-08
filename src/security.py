from datetime import datetime, timedelta, timezone
from typing import Annotated
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from .config import settings
from . import crud, schemas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        owner_id: str = payload.get("sub")
        if owner_id is None:
            raise credentials_exception
        token_data = schemas.TokenData(owner_id=owner_id)
    except JWTError:
        raise credentials_exception
    return int(token_data.owner_id)

def authenticate_owner(db: Session, email: str, password: str):
    owner = crud.get_owner_by_email(db, email)
    if not owner:
        return False
    if not verify_password(password, owner.hashed_password):
        return False
    return owner
