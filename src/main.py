from fastapi import FastAPI, Depends, HTTPException, Request, Response, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import pytz

from . import crud, models, schemas, security, notifications
from .database import SessionLocal, engine
from .config import settings
from .i18n import get_locale, gettext

# Ensure all models are created in the database
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

templates = Jinja2Templates(directory="templates")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Admin authentication dependency (simplified for example)
def get_current_admin_user(request: Request, db: Session = Depends(get_db)):
    # In a real application, this would involve JWT verification for an admin role
    # For now, let's assume a simple check or a placeholder admin user
    # For this task, we will assume an admin user is authenticated
    # and we can retrieve an owner_id from the URL path or query params for managing their data.
    # This needs to be replaced with actual admin authentication and authorization.
    # For the purpose of this task, we will allow access if a specific header is present
    # or if a hardcoded admin user is simulated.
    # THIS IS A SIMPLIFICATION AND SHOULD BE REPLACED WITH PROPER AUTHZ IN PRODUCTION
    if request.headers.get("X-Admin-Auth") == "admin_secret_key":
        return {"username": "admin"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated as admin")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, response: Response, db: Session = Depends(get_db)):
    locale = get_locale(request)
    response.set_cookie(key="locale", value=locale)
    return templates.TemplateResponse("home.html", {"request": request, "_": gettext, "locale": locale})

# --- Owner Authentication and Dashboard (Simplified) ---

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request, db: Session = Depends(get_db)): # Assuming owner is authenticated
    locale = get_locale(request)
    # Placeholder for authenticated owner
    owner_id = 1 # Replace with actual authenticated owner_id
    owner = crud.get_owner(db, owner_id=owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    upcoming_bookings = crud.get_owner_upcoming_bookings(db, owner_id=owner_id)
    
    # Analytics data (placeholder for now)
    monthly_bookings = crud.get_monthly_bookings_for_owner(db, owner_id=owner_id)
    popular_services = crud.get_popular_services_for_owner(db, owner_id=owner_id)

    return templates.TemplateResponse(
        "dashboard.html", 
        {"request": request, "owner": owner, "upcoming_bookings": upcoming_bookings, 
         "monthly_bookings": monthly_bookings, "popular_services": popular_services, 
         "_": gettext, "locale": locale}
    )

# --- Public Booking Page ---

@app.get("/bookslot.app/{owner_name}", response_class=HTMLResponse)
async def public_booking_page(request: Request, response: Response, owner_name: str, db: Session = Depends(get_db)):
    locale = get_locale(request)
    response.set_cookie(key="locale", value=locale)
    owner = crud.get_owner_by_name(db, owner_name=owner_name)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    services = crud.get_owner_services(db, owner_id=owner.id)
    available_slots = crud.get_available_slots_for_owner(db, owner_id=owner.id, date=datetime.now(pytz.utc).date())
    return templates.TemplateResponse(
        "booking_page.html", 
        {"request": request, "owner": owner, "services": services, "available_slots": available_slots, "_": gettext, "locale": locale}
    )

@app.post("/bookslot.app/{owner_name}/book")
async def submit_booking(request: Request, owner_name: str, db: Session = Depends(get_db),
                         customer_name: str = Form(...), customer_email: str = Form(...),
                         customer_phone: str = Form(None), service_id: int = Form(...),
                         booking_date: str = Form(...), booking_time: str = Form(...)):
    locale = get_locale(request)
    owner = crud.get_owner_by_name(db, owner_name=owner_name)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    # Combine date and time to a datetime object
    try:
        booking_datetime_str = f"{booking_date} {booking_time}"
        booking_datetime_local = datetime.strptime(booking_datetime_str, "%Y-%m-%d %H:%M")
        # Assume owner's timezone or convert to UTC for storage
        booking_datetime_utc = pytz.timezone('UTC').localize(booking_datetime_local) # Simplified
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date or time format")

    service = crud.get_service(db, service_id=service_id)
    if not service or service.owner_id != owner.id:
        raise HTTPException(status_code=404, detail="Service not found or does not belong to this owner")

    # Check availability (simplified, needs robust implementation)
    is_available = crud.check_slot_availability(db, owner.id, service_id, booking_datetime_utc, service.duration)
    if not is_available:
        raise HTTPException(status_code=400, detail="Selected slot is not available.")

    booking_create = schemas.BookingCreate(
        owner_id=owner.id,
        service_id=service_id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        booking_time=booking_datetime_utc,
        status="pending"
    )
    try:
        booking = crud.create_booking(db=db, booking=booking_create)
        notifications.send_booking_confirmation_email(owner, booking, service)
        notifications.send_booking_notification_to_owner(owner, booking, service)
        return templates.TemplateResponse("booking_confirmation.html", {"request": request, "booking": booking, "_": gettext, "locale": locale})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Booking failed: {e}")

# --- Stripe Webhook Endpoint ---
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    # Placeholder for Stripe webhook handling logic
    # This would parse the event, verify the signature, and update subscription status
    return {"status": "success"}

# --- Admin Panel Routes ---

@app.get("/admin/owners", response_class=HTMLResponse)
async def admin_list_owners(request: Request, db: Session = Depends(get_db), admin_user: dict = Depends(get_current_admin_user)):
    locale = get_locale(request)
    owners = crud.get_owners(db)
    return templates.TemplateResponse("admin/owners.html", {"request": request, "owners": owners, "_": gettext, "locale": locale})

@app.get("/admin/owners/{owner_id}", response_class=HTMLResponse)
async def admin_get_owner(request: Request, owner_id: int, db: Session = Depends(get_db), admin_user: dict = Depends(get_current_admin_user)):
    locale = get_locale(request)
    owner = crud.get_owner(db, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    return templates.TemplateResponse("admin/owner_detail.html", {"request": request, "owner": owner, "_": gettext, "locale": locale})

# Admin: List Services for an Owner
@app.get("/admin/owners/{owner_id}/services", response_class=HTMLResponse)
async def admin_list_owner_services(request: Request, owner_id: int, db: Session = Depends(get_db), admin_user: dict = Depends(get_current_admin_user)):
    locale = get_locale(request)
    owner = crud.get_owner(db, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    services = crud.get_owner_services(db, owner_id=owner_id)
    return templates.TemplateResponse("admin/owner_services.html", {"request": request, "owner": owner, "services": services, "_": gettext, "locale": locale})

# Admin: Add New Service for an Owner
@app.post("/admin/owners/{owner_id}/services", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def admin_create_owner_service(request: Request, owner_id: int, db: Session = Depends(get_db), admin_user: dict = Depends(get_current_admin_user),
                                     name: str = Form(...), description: str = Form(...), price: float = Form(...), duration: int = Form(...)):
    service_create = schemas.ServiceCreate(name=name, description=description, price=price, duration=duration, owner_id=owner_id)
    crud.create_owner_service(db, owner_id=owner_id, service=service_create)
    return RedirectResponse(url=f"/admin/owners/{owner_id}/services", status_code=status.HTTP_302_FOUND)

# Admin: Update Service for an Owner
@app.post("/admin/owners/{owner_id}/services/{service_id}/update", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def admin_update_owner_service(request: Request, owner_id: int, service_id: int, db: Session = Depends(get_db), admin_user: dict = Depends(get_current_admin_user),
                                     name: str = Form(...), description: str = Form(...), price: float = Form(...), duration: int = Form(...)):
    service_update = schemas.ServiceUpdate(name=name, description=description, price=price, duration=duration)
    crud.update_owner_service(db, service_id=service_id, service=service_update)
    return RedirectResponse(url=f"/admin/owners/{owner_id}/services", status_code=status.HTTP_302_FOUND)

# Admin: Delete Service for an Owner
@app.post("/admin/owners/{owner_id}/services/{service_id}/delete", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def admin_delete_owner_service(request: Request, owner_id: int, service_id: int, db: Session = Depends(get_db), admin_user: dict = Depends(get_current_admin_user)):
    crud.delete_service(db, service_id=service_id)
    return RedirectResponse(url=f"/admin/owners/{owner_id}/services", status_code=status.HTTP_302_FOUND)

# Admin: List Bookings for an Owner
@app.get("/admin/owners/{owner_id}/bookings", response_class=HTMLResponse)
async def admin_list_owner_bookings(request: Request, owner_id: int, db: Session = Depends(get_db), admin_user: dict = Depends(get_current_admin_user)):
    locale = get_locale(request)
    owner = crud.get_owner(db, owner_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    bookings = crud.get_owner_bookings(db, owner_id=owner_id)
    return templates.TemplateResponse("admin/owner_bookings.html", {"request": request, "owner": owner, "bookings": bookings, "_": gettext, "locale": locale})

# Admin: Cancel Booking for an Owner
@app.post("/admin/owners/{owner_id}/bookings/{booking_id}/cancel", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def admin_cancel_owner_booking(request: Request, owner_id: int, booking_id: int, db: Session = Depends(get_db), admin_user: dict = Depends(get_current_admin_user)):
    crud.cancel_booking(db, booking_id=booking_id)
    return RedirectResponse(url=f"/admin/owners/{owner_id}/bookings", status_code=status.HTTP_302_FOUND)

# Admin: Update Booking Status (e.g., confirm, complete)
@app.post("/admin/owners/{owner_id}/bookings/{booking_id}/update_status", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def admin_update_owner_booking_status(request: Request, owner_id: int, booking_id: int, db: Session = Depends(get_db), admin_user: dict = Depends(get_current_admin_user),
                                          status: str = Form(...)):
    crud.update_booking_status(db, booking_id=booking_id, new_status=status)
    return RedirectResponse(url=f"/admin/owners/{owner_id}/bookings", status_code=status.HTTP_302_FOUND)
