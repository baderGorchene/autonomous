from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timedelta, date, datetime, time
from typing import List, Dict, Any, Optional
import uuid
import json
import stripe

from . import models, schemas, crud, security, database, notifications, i18n, availability_utils, analytics
from .config import settings

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Setup i18n
i18n.setup_i18n(app, templates)

# Dependency to get DB session
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Stripe configuration
stripe.api_key = settings.STRIPE_API_KEY

# --- Helper functions ---
def get_current_owner(request: Request, db: Session = Depends(get_db)) -> models.Owner:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.cookies.get("access_token")
    if not token:
        raise credentials_exception
    
    try:
        email = security.get_email_from_token(token)
        if email is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    
    owner = crud.get_owner_by_email(db, email=email)
    if owner is None:
        raise credentials_exception
    return owner

def get_current_owner_or_none(request: Request, db: Session = Depends(get_db)) -> Optional[models.Owner]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        email = security.get_email_from_token(token)
        if email is None:
            return None
    except Exception:
        return None
    owner = crud.get_owner_by_email(db, email=email)
    return owner

# --- Root and Auth Endpoints ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db), owner: Optional[models.Owner] = Depends(get_current_owner_or_none)):
    if owner:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("index.html", {"request": request, "owner": owner})

@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request, owner: Optional[models.Owner] = Depends(get_current_owner_or_none)):
    if owner:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup", response_class=HTMLResponse)
async def signup(request: Request, email: str = Form(...), password: str = Form(...), name: str = Form(...), phone_number: Optional[str] = Form(None), db: Session = Depends(get_db)):
    owner = crud.get_owner_by_email(db, email=email)
    if owner:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Email already registered"})
    
    owner_in = schemas.OwnerCreate(email=email, password=password, name=name, phone_number=phone_number)
    crud.create_owner(db=db, owner=owner_in)
    return templates.TemplateResponse("signup_success.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, owner: Optional[models.Owner] = Depends(get_current_owner_or_none)):
    if owner:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_owner(db, form_data.username, form_data.password)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": owner.email}, expires_delta=access_token_expires
    )
    response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="Lax", secure=True, expires=access_token_expires.total_seconds())
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

# --- Owner Dashboard Endpoints ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    services = crud.get_owner_services(db, owner_id=owner.id)
    bookings = crud.get_owner_upcoming_bookings(db, owner_id=owner.id)

    # Analytics data
    monthly_bookings = analytics.get_monthly_bookings_data(db, owner.id)
    popular_services = analytics.get_popular_services_data(db, owner.id)

    return templates.TemplateResponse(
        "dashboard.html", 
        {
            "request": request, 
            "owner": owner, 
            "services": services, 
            "bookings": bookings,
            "monthly_bookings": monthly_bookings,
            "popular_services": popular_services
        }
    )

@app.post("/owner/profile", response_class=HTMLResponse)
async def update_owner_profile(request: Request, name: str = Form(...), phone_number: Optional[str] = Form(None), owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    try:
        owner_update = schemas.OwnerUpdate(name=name, phone_number=phone_number)
        crud.update_owner(db, owner_id=owner.id, owner_update=owner_update)
        return RedirectResponse(url="/dashboard?success=profile_updated", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        return templates.TemplateResponse("dashboard.html", {"request": request, "owner": owner, "error": f"Error updating profile: {e}"})

# --- Service Endpoints ---
@app.post("/services", response_class=HTMLResponse)
async def create_service(request: Request, name: str = Form(...), description: Optional[str] = Form(None), duration_minutes: int = Form(...), price: int = Form(...), owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    try:
        service_in = schemas.ServiceCreate(name=name, description=description, duration_minutes=duration_minutes, price=price)
        crud.create_owner_service(db=db, service=service_in, owner_id=owner.id)
        return RedirectResponse(url="/dashboard?success=service_added", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        # In a real app, you'd want to render the dashboard with the error message
        print(f"Error creating service: {e}")
        return RedirectResponse(url="/dashboard?error=service_add_failed", status_code=status.HTTP_302_FOUND)

@app.post("/services/{service_id}/update", response_class=HTMLResponse)
async def update_service(request: Request, service_id: int, name: str = Form(...), description: Optional[str] = Form(None), duration_minutes: int = Form(...), price: int = Form(...), owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    try:
        service_update = schemas.ServiceUpdate(name=name, description=description, duration_minutes=duration_minutes, price=price)
        crud.update_service(db, service_id=service_id, owner_id=owner.id, service_update=service_update)
        return RedirectResponse(url="/dashboard?success=service_updated", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error updating service: {e}")
        return RedirectResponse(url="/dashboard?error=service_update_failed", status_code=status.HTTP_302_FOUND)

@app.post("/services/{service_id}/delete", response_class=HTMLResponse)
async def delete_service(request: Request, service_id: int, owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    try:
        crud.delete_service(db, service_id=service_id, owner_id=owner.id)
        return RedirectResponse(url="/dashboard?success=service_deleted", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error deleting service: {e}")
        return RedirectResponse(url="/dashboard?error=service_delete_failed", status_code=status.HTTP_302_FOUND)

# --- Availability Endpoints ---
@app.post("/availabilities", response_class=HTMLResponse)
async def create_availability(
    request: Request,
    start_time: time = Form(...),
    end_time: time = Form(...),
    service_id: Optional[int] = Form(None),
    date: Optional[date] = Form(None),
    recurrence_type: models.RecurrenceType = Form(models.RecurrenceType.NONE),
    recurrence_value: Optional[str] = Form(None),
    recurrence_start_date: Optional[date] = Form(None),
    recurrence_end_date: Optional[date] = Form(None),
    owner: models.Owner = Depends(get_current_owner),
    db: Session = Depends(get_db)
):
    try:
        availability_in = schemas.AvailabilityCreate(
            start_time=start_time,
            end_time=end_time,
            service_id=service_id,
            date=date,
            recurrence_type=recurrence_type,
            recurrence_value=recurrence_value,
            recurrence_start_date=recurrence_start_date,
            recurrence_end_date=recurrence_end_date
        )
        crud.create_owner_availability(db=db, availability=availability_in, owner_id=owner.id)
        return RedirectResponse(url="/dashboard?success=availability_added", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error creating availability: {e}")
        return RedirectResponse(url="/dashboard?error=availability_add_failed", status_code=status.HTTP_302_FOUND)

@app.post("/availabilities/{availability_id}/delete", response_class=HTMLResponse)
async def delete_availability(request: Request, availability_id: int, owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    try:
        crud.delete_availability(db, availability_id=availability_id, owner_id=owner.id)
        return RedirectResponse(url="/dashboard?success=availability_deleted", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error deleting availability: {e}")
        return RedirectResponse(url="/dashboard?error=availability_delete_failed", status_code=status.HTTP_302_FOUND)

# --- Public Booking Page Endpoints ---
@app.get("/{owner_name}", response_class=HTMLResponse)
async def public_booking_page(request: Request, owner_name: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_name(db, name=owner_name)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    services = crud.get_owner_services(db, owner_id=owner.id)

    # Get messages for i18n
    _ = request.state.gettext

    return templates.TemplateResponse(
        "booking_page.html", 
        {
            "request": request, 
            "owner": owner, 
            "services": services,
            "today": date.today(),
            "_": _ # Pass gettext function to template
        }
    )

@app.get("/{owner_name}/api/services", response_model=List[schemas.Service])
async def get_owner_services_api(owner_name: str, db: Session = Depends(get_db)):
    owner = crud.get_owner_by_name(db, name=owner_name)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return crud.get_owner_services(db, owner_id=owner.id)

@app.get("/{owner_name}/api/available_slots", response_model=List[time])
async def get_available_slots_api(
    owner_name: str,
    service_id: int,
    selected_date: date,
    db: Session = Depends(get_db)
):
    owner = crud.get_owner_by_name(db, name=owner_name)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    
    service = crud.get_service(db, service_id=service_id, owner_id=owner.id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found for this owner")
    
    # Ensure the target_date is not in the past
    if selected_date < date.today():
        return [] # No slots for past dates

    return availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, selected_date, service.duration_minutes
    )

@app.post("/{owner_name}/book", response_class=HTMLResponse)
async def create_booking(
    request: Request,
    owner_name: str,
    customer_name: str = Form(...),
    customer_email: EmailStr = Form(...),
    customer_phone_number: Optional[str] = Form(None),
    service_id: int = Form(...),
    date: date = Form(...),
    time: time = Form(...),
    is_recurring: bool = Form(False),
    recurrence_type: models.RecurrenceType = Form(models.RecurrenceType.NONE),
    recurrence_value: Optional[str] = Form(None),
    recurrence_end_date: Optional[date] = Form(None),
    db: Session = Depends(get_db)
):
    _ = request.state.gettext # Get text for i18n
    owner = crud.get_owner_by_name(db, name=owner_name)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner not found"))

    service = crud.get_service(db, service_id=service_id, owner_id=owner.id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Service not found for this owner"))

    # Check if the requested slot is actually available
    available_slots = availability_utils.get_available_slots_for_day(
        db, owner.id, service.id, date, service.duration_minutes
    )
    if time not in available_slots:
        return templates.TemplateResponse(
            "booking_page.html", 
            {
                "request": request, 
                "owner": owner, 
                "services": crud.get_owner_services(db, owner.id),
                "today": date.today(),
                "error": _("The selected time slot is no longer available. Please choose another."),
                "_": _
            }
        )
    
    # Handle customer account linking/creation
    customer_obj: Optional[models.Customer] = None
    if customer_email:
        customer_obj = crud.get_customer_by_email(db, email=customer_email)
        if not customer_obj and customer_name and customer_phone_number:
            # Create new customer if details are sufficient
            customer_create_data = schemas.CustomerCreate(
                name=customer_name,
                email=customer_email,
                phone_number=customer_phone_number
            )
            customer_obj = crud.create_customer(db, customer_create_data)
    
    booking_in = schemas.BookingCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone_number=customer_phone_number,
        service_id=service_id,
        date=date,
        time=time,
        is_recurring=is_recurring,
        recurrence_type=recurrence_type,
        recurrence_value=recurrence_value,
        recurrence_end_date=recurrence_end_date
    )

    try:
        # Pass customer_id if a customer object was found/created
        booking = crud.create_owner_booking(db, booking=booking_in, owner_id=owner.id, customer_id=customer_obj.id if customer_obj else None)
        
        # Send notifications
        notifications.send_booking_confirmation_to_customer(owner, service, booking)
        notifications.send_new_booking_notification_to_owner(owner, service, booking)

        return templates.TemplateResponse(
            "booking_confirmation.html", 
            {
                "request": request, 
                "owner": owner, 
                "service": service, 
                "booking": booking,
                "_": _
            }
        )
    except Exception as e:
        print(f"Booking creation failed: {e}")
        return templates.TemplateResponse(
            "booking_page.html", 
            {
                "request": request, 
                "owner": owner, 
                "services": crud.get_owner_services(db, owner.id),
                "today": date.today(),
                "error": _("Failed to create booking. Please try again."),
                "_": _
            }
        )

# --- Subscription Endpoints ---
@app.get("/subscription", response_class=HTMLResponse)
async def subscription_management(request: Request, owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    _ = request.state.gettext
    return templates.TemplateResponse("subscription.html", {"request": request, "owner": owner, "_": _})

@app.post("/create-checkout-session", response_model=schemas.CreateCheckoutSessionResponse)
async def create_checkout_session(request: Request, owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    try:
        # Create a new Stripe Customer if the owner doesn't have one
        if not owner.stripe_customer_id:
            stripe_customer = stripe.Customer.create(email=owner.email, name=owner.name)
            owner.stripe_customer_id = stripe_customer.id
            db.add(owner)
            db.commit()
            db.refresh(owner)

        checkout_session = stripe.checkout.Session.create(
            customer=owner.stripe_customer_id,
            line_items=[
                {
                    'price': settings.STRIPE_PREMIUM_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=request.url_for('subscription_success') + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.url_for('subscription_management'),
        )
        return schemas.CreateCheckoutSessionResponse(session_id=checkout_session.id, public_key=os.environ.get("STRIPE_PUBLIC_KEY", "pk_test_..."))
    except Exception as e:
        print(f"Error creating checkout session: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/subscription/success", response_class=HTMLResponse)
async def subscription_success(request: Request, session_id: str, owner: models.Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    _ = request.state.gettext
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        if checkout_session.payment_status == "paid":
            # Update owner's subscription status in DB
            owner.subscription_status = "premium"
            db.add(owner)
            db.commit()
            db.refresh(owner)
            return templates.TemplateResponse("subscription_success.html", {"request": request, "owner": owner, "_": _})
        else:
            return templates.TemplateResponse("subscription_failure.html", {"request": request, "owner": owner, "error": _("Payment not completed."), "_": _})
    except Exception as e:
        print(f"Error retrieving checkout session: {e}")
        return templates.TemplateResponse("subscription_failure.html", {"request": request, "owner": owner, "error": str(e), "_": _})

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_id = session.get('customer')
        if session.get('payment_status') == 'paid' and customer_id:
            owner = crud.get_owner_by_stripe_customer_id(db, stripe_customer_id=customer_id)
            if owner:
                owner.subscription_status = "premium"
                db.add(owner)
                db.commit()
                db.refresh(owner)
                print(f"Owner {owner.email} subscription upgraded to premium.")
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        owner = crud.get_owner_by_stripe_customer_id(db, stripe_customer_id=customer_id)
        if owner:
            owner.subscription_status = "cancelled"
            db.add(owner)
            db.commit()
            db.refresh(owner)
            print(f"Owner {owner.email} subscription cancelled.")
    # ... handle other event types

    return {"status": "success"}

# --- Admin Panel Endpoints ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db), owner: models.Owner = Depends(get_current_owner)):
    if owner.email != "admin@bookslot.app": # Simple admin check for now
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    all_owners = crud.get_all_owners(db)
    return templates.TemplateResponse("admin/dashboard.html", {"request": request, "owners": all_owners})

@app.get("/admin/owners/{owner_id}", response_class=HTMLResponse)
async def admin_view_owner(request: Request, owner_id: int, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    owner = crud.get_owner(db, owner_id)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    
    services = crud.get_owner_services(db, owner_id)
    bookings = crud.get_owner_all_bookings(db, owner_id)
    availabilities = crud.get_owner_all_availabilities(db, owner_id)

    return templates.TemplateResponse("admin/owner_detail.html", {"request": request, "owner": owner, "services": services, "bookings": bookings, "availabilities": availabilities})

@app.post("/admin/owners/{owner_id}/update", response_class=HTMLResponse)
async def admin_update_owner(
    request: Request,
    owner_id: int,
    email: Optional[EmailStr] = Form(None),
    name: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    subscription_status: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    owner_update = schemas.AdminOwnerUpdate(
        email=email,
        name=name,
        phone_number=phone_number,
        is_active=is_active if is_active is not None else None,
        subscription_status=subscription_status
    )
    
    try:
        crud.update_owner(db, owner_id, owner_update)
        return RedirectResponse(url=f"/admin/owners/{owner_id}?success=owner_updated", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error updating owner: {e}")
        return RedirectResponse(url=f"/admin/owners/{owner_id}?error=owner_update_failed", status_code=status.HTTP_302_FOUND)

@app.post("/admin/owners/{owner_id}/delete", response_class=HTMLResponse)
async def admin_delete_owner(request: Request, owner_id: int, db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    try:
        crud.delete_owner(db, owner_id)
        return RedirectResponse(url="/admin?success=owner_deleted", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error deleting owner: {e}")
        return RedirectResponse(url=f"/admin/owners/{owner_id}?error=owner_delete_failed", status_code=status.HTTP_302_FOUND)

@app.post("/admin/services/{service_id}/update", response_class=HTMLResponse)
async def admin_update_service(
    request: Request,
    service_id: int,
    owner_id: int = Form(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    duration_minutes: Optional[int] = Form(None),
    price: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    service_update = schemas.AdminServiceUpdate(
        name=name,
        description=description,
        duration_minutes=duration_minutes,
        price=price
    )
    try:
        crud.update_service(db, service_id, owner_id, service_update)
        return RedirectResponse(url=f"/admin/owners/{owner_id}?success=service_updated", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error updating service: {e}")
        return RedirectResponse(url=f"/admin/owners/{owner_id}?error=service_update_failed", status_code=status.HTTP_302_FOUND)

@app.post("/admin/services/{service_id}/delete", response_class=HTMLResponse)
async def admin_delete_service(request: Request, service_id: int, owner_id: int = Form(...), db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    try:
        crud.delete_service(db, service_id, owner_id) # Need owner_id to verify ownership
        return RedirectResponse(url=f"/admin/owners/{owner_id}?success=service_deleted", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error deleting service: {e}")
        return RedirectResponse(url=f"/admin/owners/{owner_id}?error=service_delete_failed", status_code=status.HTTP_302_FOUND)

@app.post("/admin/bookings/{booking_id}/update", response_class=HTMLResponse)
async def admin_update_booking(
    request: Request,
    booking_id: int,
    owner_id: int = Form(...),
    customer_name: Optional[str] = Form(None),
    customer_email: Optional[EmailStr] = Form(None),
    customer_phone_number: Optional[str] = Form(None),
    date: Optional[date] = Form(None),
    time: Optional[time] = Form(None),
    is_recurring: Optional[bool] = Form(None),
    recurrence_type: Optional[models.RecurrenceType] = Form(None),
    recurrence_value: Optional[str] = Form(None),
    recurrence_end_date: Optional[date] = Form(None),
    db: Session = Depends(get_db),
    current_owner: models.Owner = Depends(get_current_owner)
):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    booking_update = schemas.AdminBookingUpdate(
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone_number=customer_phone_number,
        date=date,
        time=time,
        is_recurring=is_recurring,
        recurrence_type=recurrence_type,
        recurrence_value=recurrence_value,
        recurrence_end_date=recurrence_end_date
    )
    try:
        crud.update_booking(db, booking_id, owner_id, booking_update)
        return RedirectResponse(url=f"/admin/owners/{owner_id}?success=booking_updated", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error updating booking: {e}")
        return RedirectResponse(url=f"/admin/owners/{owner_id}?error=booking_update_failed", status_code=status.HTTP_302_FOUND)

@app.post("/admin/bookings/{booking_id}/delete", response_class=HTMLResponse)
async def admin_delete_booking(request: Request, booking_id: int, owner_id: int = Form(...), db: Session = Depends(get_db), current_owner: models.Owner = Depends(get_current_owner)):
    if current_owner.email != "admin@bookslot.app":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    try:
        crud.delete_booking(db, booking_id, owner_id) # Need owner_id to verify ownership
        return RedirectResponse(url=f"/admin/owners/{owner_id}?success=booking_deleted", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error deleting booking: {e}")
        return RedirectResponse(url=f"/admin/owners/{owner_id}?error=booking_delete_failed", status_code=status.HTTP_302_FOUND)
