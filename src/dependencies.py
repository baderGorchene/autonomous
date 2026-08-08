from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from . import crud, security, schemas
from jose import JWTError
from src.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

async def get_current_owner(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        token = request.cookies.get("access_token")
        if token and token.startswith("Bearer%20"):
            token = token.replace("Bearer%20", "Bearer ")
        elif token and token.startswith("Bearer "):
            pass
        else:
            token = None

    if token is None:
        raise credentials_exception

    token_value = token.split(" ")[1] if token.startswith("Bearer ") else token

    try:
        payload = security.decode_access_token(token_value)
        if payload is None:
            raise credentials_exception
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    owner = crud.get_owner_by_email(db, email=token_data.email)
    if owner is None:
        raise credentials_exception
    return owner
