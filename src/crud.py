from sqlalchemy.orm import Session
from . import models, schemas
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def create_owner(db: Session, owner: schemas.OwnerCreate):
    hashed_password = get_password_hash(owner.password)
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, name=owner.name, phone_number=owner.phone_number, locale=owner.locale)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def get_owner(db: Session, owner_id: int):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owner_services(db: Session, owner_id: int):
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).all()

def get_service(db: Session, service_id: int):
    return db.query(models.Service).filter(models.Service.id == service_id).first()

def create_booking(db: Session, booking: schemas.BookingCreate):
    db_booking = models.Booking(
        owner_id=booking.owner_id,
        service_id=booking.service_id,
        customer_id=booking.customer_id, # This is the key update here
        date=booking.date,
        time=booking.time,
        is_confirmed=True,
        recurrence_id=booking.recurrence_id
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking
