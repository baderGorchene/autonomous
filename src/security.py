import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from . import models

# Logging setup
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
reusable_oauth2 = OAuth2PasswordBearer(tokenUrl="/token") # Use this for owners

# For customers, if a separate token URL is desired
oauth2_customer_scheme = OAuth2PasswordBearer(tokenUrl="customer-token") 

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Error during password verification: {e}")
        return False

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def authenticate_owner(db: Session, username: str, password: str):
    owner = db.query(models.Owner).filter(models.Owner.email == username).first()
    if not owner:
        return None
    if not verify_password(password, owner.hashed_password):
        logger.warning(f"Authentication failed for owner {username}: incorrect password.")
        return None
    return owner

def authenticate_customer(db: Session, email: str, password: str):
    customer = db.query(models.Customer).filter(models.Customer.email == email).first()
    if not customer:
        return None
    if not verify_password(password, customer.hashed_password):
        logger.warning(f"Authentication failed for customer {email}: incorrect password.")
        return None
    return customer

def get_current_owner(db: Session = Depends(get_db), token: str = Depends(reusable_oauth2)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        user_type: str = payload.get("user_type")
        if username is None or user_type != "owner":
            logger.warning(f"Invalid token payload for owner: username={username}, user_type={user_type}")
            raise credentials_exception
    except JWTError as e:
        logger.error(f"JWT decoding error for owner token: {e}")
        raise credentials_exception
    owner = db.query(models.Owner).filter(models.Owner.email == username).first()
    if owner is None:
        logger.warning(f"Owner not found for token subject: {username}")
        raise credentials_exception
    return owner

def get_current_customer(db: Session = Depends(get_db), token: str = Depends(reusable_oauth2)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        user_type: str = payload.get("user_type")
        if email is None or user_type != "customer":
            logger.warning(f"Invalid token payload for customer: email={email}, user_type={user_type}")
            raise credentials_exception
    except JWTError as e:
        logger.error(f"JWT decoding error for customer token: {e}")
        raise credentials_exception
    customer = db.query(models.Customer).filter(models.Customer.email == email).first()
    if customer is None:
        logger.warning(f"Customer not found for token subject: {email}")
        raise credentials_exception
    return customer
