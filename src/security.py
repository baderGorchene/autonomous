from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from . import models, schemas, config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=config.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.settings.SECRET_KEY, algorithm=config.settings.ALGORITHM)
    return encoded_jwt

# --- Owner Security ---
def get_owner_by_username(db: Session, username: str):
    return db.query(models.Owner).filter(models.Owner.username == username).first()

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def create_owner(db: Session, owner: schemas.OwnerCreate):
    hashed_password = get_password_hash(owner.password)
    db_owner = models.Owner(
        username=owner.username, email=owner.email, hashed_password=hashed_password,
        full_name=owner.full_name, phone_number=owner.phone_number
    )
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def authenticate_owner(db: Session, username: str, password: str):
    owner = get_owner_by_username(db, username)
    if not owner:
        return None
    if not verify_password(password, owner.hashed_password):
        return None
    return owner

def get_current_owner_from_token(token: str, db: Session):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.settings.SECRET_KEY, algorithms=[config.settings.ALGORITHM])
        username: str = payload.get("sub")
        scope: str = payload.get("scope")
        if username is None or scope != "owner":
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception
    owner = get_owner_by_username(db, username=token_data.username)
    if owner is None:
        raise credentials_exception
    return owner

def update_owner(db: Session, current_owner: models.Owner, owner_update: schemas.OwnerUpdate):
    for key, value in owner_update.dict(exclude_unset=True).items():
        if key == "email" and value != current_owner.email:
            existing_owner = get_owner_by_email(db, email=value)
            if existing_owner and existing_owner.id != current_owner.id:
                raise ValueError("Email already registered by another owner.")
        setattr(current_owner, key, value)
    db.commit()
    db.refresh(current_owner)
    return current_owner

# --- Customer Security ---
def get_customer_by_email(db: Session, email: str):
    return db.query(models.Customer).filter(models.Customer.email == email).first()

def create_customer(db: Session, customer: schemas.CustomerCreate):
    hashed_password = get_password_hash(customer.password) if customer.password else None
    db_customer = models.Customer(
        email=customer.email, hashed_password=hashed_password,
        full_name=customer.full_name, phone_number=customer.phone_number
    )
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

def authenticate_customer(db: Session, email: str, password: str):
    customer = get_customer_by_email(db, email)
    if not customer or not customer.hashed_password:
        return None
    if not verify_password(password, customer.hashed_password):
        return None
    return customer

def get_current_customer_from_token(token: str, db: Session):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.settings.SECRET_KEY, algorithms=[config.settings.ALGORITHM])
        email: str = payload.get("sub")
        scope: str = payload.get("scope")
        if email is None or scope != "customer":
            raise credentials_exception
        token_data = schemas.TokenData(username=email)
    except JWTError:
        raise credentials_exception
    customer = get_customer_by_email(db, email=token_data.username)
    if customer is None:
        raise credentials_exception
    return customer

def update_customer(db: Session, current_customer: models.Customer, customer_update: schemas.CustomerUpdate):
    for key, value in customer_update.dict(exclude_unset=True).items():
        if key == "email" and value != current_customer.email:
            existing_customer = get_customer_by_email(db, email=value)
            if existing_customer and existing_customer.id != current_customer.id:
                raise ValueError("Email already registered by another customer.")
        setattr(current_customer, key, value)
    db.commit()
    db.refresh(current_customer)
    return current_customer