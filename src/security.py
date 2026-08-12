from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer

from . import models, schemas, crud
from .database import get_db
from .config import settings

# Import the security logger
from .main import security_logger

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def authenticate_owner(db: Session, email: str, password: str, client_ip: str) -> Optional[models.Owner]:
    owner = crud.get_owner_by_email(db, email)
    if not owner or not verify_password(password, owner.hashed_password):
        security_logger.warning(
            "OWNER_AUTH_FAILED",
            extra={"client_ip": client_ip, "username": email}
        )
        return None
    security_logger.info(
        "OWNER_AUTH_SUCCESS",
        extra={"client_ip": client_ip, "username": email}
    )
    return owner

async def get_current_owner(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        owner_id: str = payload.get("sub")
        if owner_id is None:
            security_logger.warning(
                "OWNER_TOKEN_INVALID: No owner_id in token payload",
                extra={"client_ip": request.client.host, "username": "N/A"}
            )
            raise credentials_exception
        token_data = schemas.TokenData(owner_id=owner_id)
    except JWTError:
        security_logger.warning(
            "OWNER_TOKEN_INVALID: JWTError",
            extra={"client_ip": request.client.host, "username": "N/A"}
        )
        raise credentials_exception
    owner = crud.get_owner(db, owner_id=token_data.owner_id)
    if owner is None:
        security_logger.warning(
            "OWNER_NOT_FOUND_FOR_TOKEN",
            extra={"client_ip": request.client.host, "username": token_data.owner_id}
        )
        raise credentials_exception
    return owner

def authenticate_customer(db: Session, email: str, password: str, client_ip: str) -> Optional[models.Customer]:
    customer = crud.get_customer_by_email(db, email)
    if not customer or not verify_password(password, customer.hashed_password):
        security_logger.warning(
            "CUSTOMER_AUTH_FAILED",
            extra={"client_ip": client_ip, "username": email}
        )
        return None
    security_logger.info(
        "CUSTOMER_AUTH_SUCCESS",
        extra={"client_ip": client_ip, "username": email}
    )
    return customer

async def get_current_customer(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        customer_id: str = payload.get("sub")
        if customer_id is None:
            security_logger.warning(
                "CUSTOMER_TOKEN_INVALID: No customer_id in token payload",
                extra={"client_ip": request.client.host, "username": "N/A"}
            )
            raise credentials_exception
        token_data = schemas.TokenData(owner_id=customer_id) # Assuming TokenData is generic enough, or adjust schema
    except JWTError:
        security_logger.warning(
            "CUSTOMER_TOKEN_INVALID: JWTError",
            extra={"client_ip": request.client.host, "username": "N/A"}
        )
        raise credentials_exception
    customer = crud.get_customer(db, customer_id=token_data.owner_id) # Using owner_id as generic user_id
    if customer is None:
        security_logger.warning(
            "CUSTOMER_NOT_FOUND_FOR_TOKEN",
            extra={"client_ip": request.client.host, "username": token_data.owner_id}
        )
        raise credentials_exception
    return customer
