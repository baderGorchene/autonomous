from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, database

router = APIRouter()

@router.get("/{slug}")
def get_booking_page(slug: str, request: Request, db: Session = Depends(lambda: database.SessionLocal())):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Business not found")
    return request.state.templates.TemplateResponse("booking_page.html", {
        "request": request, 
        "owner": owner, 
        "services": owner.services_json or [],
        "lang": request.state.locale
    })