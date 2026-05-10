from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session
from .. import models, database

router = APIRouter()

@router.post("/signup")
def signup(
    name: str = Form(...),
    email: str = Form(...),
    business_name: str = Form(...),
    slug: str = Form(...),
    db: Session = Depends(lambda: database.SessionLocal())
):
    if db.query(models.Owner).filter(models.Owner.slug == slug).first():
        raise HTTPException(status_code=400, detail="Slug already taken")
    new_owner = models.Owner(name=name, email=email, business_name=business_name, slug=slug)
    db.add(new_owner)
    db.commit()
    return {"status": "created", "slug": slug}