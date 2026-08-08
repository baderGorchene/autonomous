from sqlalchemy.orm import Session
from . import models, schemas
from datetime import datetime, timedelta
from sqlalchemy import func, extract
from typing import Optional, List

# Admin CRUD operations
def get_admin_by_email(db: Session, email: str):
    return db.query(models.Admin).filter(models.Admin.email == email).first()

def create_admin(db: Session, admin: schemas.AdminCreate, hashed_password: str):
    db_admin = models.Admin(email=admin.email, hashed_password=hashed_password, name=admin.name)
    db.add(db_admin)
    db.commit()
    db.refresh(db_admin)
    return db_admin

# Owner CRUD operations
def get_owner_by_email(db: Session, email: str):
    return db.query(models.Owner).filter(models.Owner.email == email).first()

def create_owner(db: Session, owner: schemas.OwnerCreate, hashed_password: str):
    db_owner = models.Owner(email=owner.email, hashed_password=hashed_password, name=owner.name, phone=owner.phone, subscription_status=owner.subscription_status if owner.subscription_status else "free")
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner

def get_owner(db: Session, owner_id: int):
    return db.query(models.Owner).filter(models.Owner.id == owner_id).first()

def get_owners(db: Session, skip: int = 0, limit: int = 100) -> List[models.Owner]:
    return db.query(models.Owner).offset(skip).limit(limit).all()

def update_owner_by_admin(db: Session, owner: models.Owner, owner_update: schemas.OwnerAdminUpdate):
    update_data = owner_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(owner, field, value)
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner

def delete_owner(db: Session, owner_id: int):
    owner = db.query(models.Owner).filter(models.Owner.id == owner_id).first()
    if owner:
        db.delete(owner)
        db.commit()
        return True
    return False

def get_owner_services(db: Session, owner_id: int):
    return db.query(models.Service).filter(models.Service.owner_id == owner_id).all()

def get_service_by_id(db: Session, service_id: int):
    return db.query(models.Service).filter(models.Service.id == service_id).first()

def create_booking(db: Session, booking: schemas.BookingCreate, owner_id: int):
    db_booking = models.Booking(**booking.model_dump(), owner_id=owner_id)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def get_owner_upcoming_bookings(db: Session, owner_id: int):
    now = datetime.now()
    return db.query(models.Booking)
             .join(models.Service)
             .filter(models.Booking.owner_id == owner_id, models.Booking.booking_time >= now)
             .order_by(models.Booking.booking_time)
             .all()

def update_owner_profile(db: Session, owner: models.Owner, owner_update: schemas.OwnerProfileUpdate):
    for field, value in owner_update.model_dump(exclude_unset=True).items():
        setattr(owner, field, value)
    db.commit()
    db.refresh(owner)
    return owner

def update_owner_subscription_status(db: Session, owner: models.Owner, status: str, stripe_customer_id: Optional[str] = None, stripe_subscription_id: Optional[str] = None):
    owner.subscription_status = status
    if stripe_customer_id:
        owner.stripe_customer_id = stripe_customer_id
    if stripe_subscription_id:
        owner.stripe_subscription_id = stripe_subscription_id
    db.commit()
    db.refresh(owner)
    return owner

def get_owner_analytics(db: Session, owner_id: int):
    # Total bookings
    total_bookings = db.query(func.count(models.Booking.id)).filter(models.Booking.owner_id == owner_id).scalar()

    # Monthly bookings
    dialect_name = db.bind.dialect.name

    if 'postgresql' in dialect_name:
        month_expression = func.to_char(models.Booking.booking_time, 'YYYY-MM')
    elif 'sqlite' in dialect_name:
        month_expression = func.strftime('%Y-%m', models.Booking.booking_time)
    else:
        raise NotImplementedError(f"Monthly bookings analytics not implemented for database dialect: {dialect_name}")

    monthly_bookings_query = (
        db.query(
            month_expression.label('month'),
            func.count(models.Booking.id).label('count')
        )
        .filter(models.Booking.owner_id == owner_id)
        .group_by('month')
        .order_by('month')
        .all()
    )
    monthly_bookings = []
    for r in monthly_bookings_query:
        monthly_bookings.append({"month": r.month, "count": r.count})

    # Popular services
    popular_services_query = (
        db.query(
            models.Service.name.label('service_name'),
            func.count(models.Booking.id).label('count')
        )
        .join(models.Service, models.Booking.service_id == models.Service.id)
        .filter(models.Booking.owner_id == owner_id)
        .group_by(models.Service.name)
        .order_by(func.count(models.Booking.id).desc())
        .limit(5)
        .all()
    )
    popular_services = []
    for r in popular_services_query:
        popular_services.append({"service_name": r.service_name, "count": r.count})

    return {
        "total_bookings": total_bookings,
        "monthly_bookings": monthly_bookings,
        "popular_services": popular_services,
    }
