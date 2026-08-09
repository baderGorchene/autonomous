from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .config import settings
from . import models, schemas # schemas is not strictly needed here but good practice
from .database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_owner(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        owner_id: int = payload.get("sub")
        if owner_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    owner = await db.execute(select(models.Owner).filter(models.Owner.id == owner_id))
    owner = owner.scalar_one_or_none()
    if owner is None:
        raise credentials_exception
    return owner
