import uuid
from datetime import date, datetime, time, timedelta
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, Request, HTTPException, status, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from . import models, schemas, security, notifications, analytics
from .dependencies import get_db, get_current_owner, get_admin_user
from .config import settings
from .i18n import get_locale, gettext
from .availability_utils import get_available_slots_for_day

# Initialize Jinja2Templates
templates = Jinja2Templates(directory="templates")

# Initialize APIRouter
router = APIRouter()

# Add gettext to templates globals
templates.env.globals['gettext'] = gettext
templates.env.globals['_'] = gettext

# Babel for i18n date/time/currency formatting
from babel.dates import format_date as babel_format_date
from babel.dates import format_time as babel_format_time
from babel.numbers import format_currency as babel_format_currency

def jinja_format_date(value, locale):
    if not value: return ""
    return babel_format_date(value, format='medium', locale=locale)

def jinja_format_time(value, locale):
    if not value: return ""
    return babel_format_time(value, format='short', locale=locale)

def jinja_format_currency(value, currency, locale):
    if value is None: return ""
    return babel_format_currency(value, currency, locale=locale)

templates.env.filters['format_date'] = jinja_format_date
templates.env.filters['format_time'] = jinja_format_time
templates.env.filters['format_currency'] = jinja_format_currency


# --- Dashboard related endpoints ---
@router.get("/dashboard", response_class=HTMLResponse)
async def owner_dashboard(
    request: Request, 
    db: Session = Depends(get_db), 
    current_owner: models.Owner = Depends(get_current_owner)
):
    locale_code = request.session.get("locale", "en")
    
    today = date.today()
    
    # Fetch one-off bookings
    one_off_bookings = db.query(models.Booking).filter(
        models.Booking.owner_id == current_owner.id,
        models.Booking.is_recurring == False,
        models.Booking.date >= today
    ).order_by(models.Booking.date, models.Booking.time).all()

    # Fetch recurring series definitions and their *upcoming* occurrences
    recurring_series_list_with_occurrences = []
    recurring_series_definitions = db.query(models.RecurrenceSeries).filter(
        models.RecurrenceSeries.owner_id == current_owner.id,
        (models.RecurrenceSeries.recurrence_end_date >= today) | (models.RecurrenceSeries.recurrence_end_date.is_(None))
    ).all()

    for series_def in recurring_series_definitions:
        # Get the service name for the series
        service = db.query(models.Service).filter(models.Service.id == series_def.service_id).first()
        
        # Fetch upcoming occurrences for this series
        upcoming_occurrences = db.query(models.Booking).filter(
            models.Booking.recurrence_id == series_def.id,
            models.Booking.date >= today
        ).order_by(models.Booking.date, models.Booking.time).limit(3).all() # Limit to next 3 occurrences for dashboard view

        if service: # Only add if service exists (should always)
            recurring_series_list_with_occurrences.append({
                "recurrence_id": series_def.id,
                "service_name": service.name,
                "recurrence_type": series_def.recurrence_type, # This is an Enum, need .value in template
                "recurrence_value": series_def.recurrence_value,
                "recurrence_start_date": series_def.recurrence_start_date,
                "recurrence_end_date": series_def.recurrence_end_date,
                "next_occurrences": upcoming_occurrences
            })

    # Analytics data
    monthly_data = analytics.get_monthly_bookings_data(db, current_owner.id)
    popular_services = analytics.get_popular_services_data(db, current_owner.id)

    context = {
        "request": request,
        "owner": current_owner,
        "upcoming_one_off_bookings": one_off_bookings,
        "recurring_booking_series_list": recurring_series_list_with_occurrences,
        "monthly_bookings_data": monthly_data,
        "popular_services_data": popular_services,
        "currency_code": current_owner.currency_code, # Assuming owner has a currency_code field
        "locale_code": locale_code,
    }
    return templates.TemplateResponse("dashboard.html", context)

# --- Placeholder for other endpoints that would be in main.py ---
# @router.get("/")
# async def read_root():
#     return {"message": "Welcome to BookSlot"}

# @router.get("/health")
# async def health_check():
#     return {"status": "ok"}

# @router.get("/login", response_class=HTMLResponse)
# async def login_for_access(request: Request):
#    # ... login logic ...
#    return templates.TemplateResponse("login.html", {"request": request})

# ... other endpoints for signup, profile, services, availability, booking_page, etc.
