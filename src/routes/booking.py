from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .. import models, database
from datetime import datetime

router = APIRouter()

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{slug}/slots")
def get_available_slots(slug: str, date: str, db: Session = Depends(get_db)):
    owner = db.query(models.Owner).filter(models.Owner.slug == slug).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    # Logic to filter availability_json based on date and existing bookings
    return {"slots": ["09:00", "10:00", "11:00"]}

@router.post("/{slug}/book")
def create_booking(slug: str, customer_name: str, customer_phone: str, datetime_str: str, db: Session = Depends(get_db)):
    # 1. Validate slot availability before creating
    # 2. Save to DB
    # 3. Trigger notification
    return {"status": "success"}