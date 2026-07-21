from sqlalchemy.orm import Session
from . import models, schemas, security

def get_owner(db: Session, owner_id: int):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def get_owner_by_slug(db: Session, slug: str):
    return db.query(models.Owner).filter(models.Owner.slug == slug).first()

def get_owners(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Owner).offset(skip).limit(limit).all()

def create_owner(db: Session, owner: schemas.OwnerCreate):
    hashed_password = security.get_password_hash(owner.password)
    db_owner = models.Owner(name=owner.name, email=owner.email, hashed_password=hashed_password, business_name=owner.business_name, slug=owner.slug, services_json=[], availability_json={})
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def authenticate_owner(db: Session, email: str, password: str):
    owner = get_owner_by_email(db, email)
    if not owner:
        return False
    if not security.verify_password(password, owner.hashed_password):
        return False
    return owner

def create_booking(db: Session, booking: schemas.BookingCreate, owner_id: int):
    db_booking = models.Booking(**booking.dict(), owner_id=owner_id)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def update_owner_profile(db: Session, current_owner: models.Owner, owner_update: schemas.OwnerProfileUpdate):
    current_owner.name = owner_update.name
    current_owner.business_name = owner_update.business_name
    current_owner.phone = owner_update.phone
    db.add(current_owner)
    db.commit()
    db.refresh(current_owner)
    return current_owner