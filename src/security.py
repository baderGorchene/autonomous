from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models, schemas, database, crud
from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="owner/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def get_current_user_from_token(token: str, db: Session):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        user_type: str = payload.get("user_type")
        if email is None or user_id is None or user_type is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email, user_id=user_id, user_type=user_type)
    except JWTError:
        raise credentials_exception
    
    if token_data.user_type == "owner":
        user = crud.get_owner_by_email(db, email=token_data.email)
    elif token_data.user_type == "customer":
        user = crud.get_customer_by_email(db, email=token_data.email)
    else:
        user = None
    
    if user is None:
        raise credentials_exception
    return user

def authenticate_owner(db: Session, email: str, password: str):
    owner = crud.get_owner_by_email(db, email=email)
    if not owner or not verify_password(password, owner.hashed_password):
        return None
    return owner

def get_current_active_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    user = get_current_user_from_token(token, db)
    if user.user_type != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as owner")
    # if not user.is_active:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive owner")
    return user

def authenticate_customer(db: Session, email: str, password: str):
    customer = crud.get_customer_by_email(db, email=email)
    if not customer or not verify_password(password, customer.hashed_password):
        return None
    return customer

def get_current_active_customer(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    user = get_current_user_from_token(token, db)
    if user.user_type != "customer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as customer")
    # if not user.is_active:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive customer")
    return user