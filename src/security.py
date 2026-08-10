from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import schemas, models
from .config import settings
from .database import SessionLocal 

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="owners/token")
oauth2_customer_scheme = OAuth2PasswordBearer(tokenUrl="customers/token") 

def get_password_hash(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return schemas.TokenData(email=payload.get("sub"), user_type=payload.get("user_type"))
    except JWTError:
        return None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def authenticate_owner(db: Session, email: str, password: str):
    owner = db.query(models.Owner).filter(models.Owner.email == email).first()
    if not owner or not verify_password(password, owner.hashed_password):
        return None
    return owner

def get_current_owner(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = decode_access_token(token)
    if token_data is None or token_data.email is None:
        raise credentials_exception
    owner = db.query(models.Owner).filter(models.Owner.email == token_data.email).first()
    if owner is None:
        raise credentials_exception
    if token_data.user_type != "owner": 
        raise credentials_exception
    return owner

async def get_current_owner_optional(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token") 
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    
    if token:
        token_data = decode_access_token(token)
        if token_data and token_data.email and token_data.user_type == "owner":
            owner = db.query(models.Owner).filter(models.Owner.email == token_data.email).first()
            return owner
    return None

def authenticate_customer(db: Session, email: str, password: str):
    customer = db.query(models.Customer).filter(models.Customer.email == email).first()
    if not customer or not customer.hashed_password or not verify_password(password, customer.hashed_password):
        return None
    return customer

def get_current_customer(db: Session = Depends(get_db), token: str = Depends(oauth2_customer_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = decode_access_token(token)
    if token_data is None or token_data.email is None:
        raise credentials_exception
    customer = db.query(models.Customer).filter(models.Customer.email == token_data.email).first()
    if customer is None:
        raise credentials_exception
    if token_data.user_type != "customer": 
        raise credentials_exception
    return customer
