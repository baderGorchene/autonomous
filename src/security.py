from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_owner_access_token(owner_id: int, expires_delta: Optional[timedelta] = None) -> str:
    data = {"sub": str(owner_id), "type": "owner"}
    return create_access_token(data, expires_delta)

def create_customer_access_token(customer_id: int, owner_id: int, expires_delta: Optional[timedelta] = None) -> str:
    data = {"sub": str(customer_id), "owner_id": owner_id, "type": "customer"}
    return create_access_token(data, expires_delta)
