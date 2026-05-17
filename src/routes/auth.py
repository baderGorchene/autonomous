from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from .. import models, database

SECRET_KEY = "supersecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

router = APIRouter()

def get_current_owner(token: str = Depends(oauth2_scheme), db: Session = Depends(lambda: database.SessionLocal())):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        owner_id = payload.get("sub")
        if owner_id is None: raise HTTPException(status_code=401)
        return db.query(models.Owner).filter(models.Owner.id == int(owner_id)).first()
    except:
        raise HTTPException(status_code=401)

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.email == form_data.username).first()
    if not owner or not pwd_context.verify(form_data.password, getattr(owner, "hashed_password", "")):
        raise HTTPException(status_code=401, detail="Incorrect credentials")
    token = jwt.encode({"sub": str(owner.id), "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}