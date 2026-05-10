from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from .. import models, database

router = APIRouter()

@router.get("/{owner_slug}")
def get_booking_page(owner_slug: str, request: Request, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == owner_slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return request.state.templates.TemplateResponse("booking_page.html", {"request": request, "owner": owner, "lang": request.state.locale})