from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session
from .. import models, database

router = APIRouter()

@router.post("/settings/{owner_id}/update")
def update_settings(
    owner_id: int,
    services: str = Form(...),
    availability: str = Form(...),
    db: Session = Depends(lambda: database.SessionLocal())
):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    owner.services_json = services
    owner.availability_json = availability
    db.commit()
    return {"status": "updated"}