from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import date, timedelta
from typing import List, Dict, Any

from . import models

def get_monthly_bookings_data(db: Session, owner_id: int) -> List[Dict[str, Any]]:
    """
    Fetches monthly booking counts for the owner for the last 12 months.
    """
    today = date.today()
    monthly_data = []

    for i in range(12): # Last 12 months
        target_month = today.month - i
        target_year = today.year
        if target_month <= 0:
            target_month += 12
            target_year -= 1

        bookings_count = db.query(models.Booking).filter(
            models.Booking.owner_id == owner_id,
            extract('year', models.Booking.date) == target_year,
            extract('month', models.Booking.date) == target_month
        ).count()

        monthly_data.insert(0, { # Insert at the beginning to maintain chronological order
            "month": f"{target_year}-{target_month:02d}",
            "count": bookings_count
        })
    return monthly_data

def get_popular_services_data(db: Session, owner_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fetches the most popular services for the owner based on booking counts.
    """
    popular_services = db.query(
        models.Service.name,
        func.count(models.Booking.id).label("booking_count")
    ).join(models.Booking).filter(
        models.Booking.owner_id == owner_id,
        models.Service.owner_id == owner_id # Ensure service belongs to the owner
    ).group_by(models.Service.name).order_by(
        func.count(models.Booking.id).desc()
    ).limit(limit).all()

    return [{"service_name": name, "booking_count": count} for name, count in popular_services]
