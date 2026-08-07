import stripe
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from src.config import settings
from src.database import get_db
from src.models import Owner, Service, Booking, PaymentStatus, BookingStatus
from src.schemas import BookingCreate, BookingInDB
from src.notifications import send_booking_confirmation_email, send_owner_booking_notification, send_whatsapp_message
from src.i18n import get_locale, gettext_for_locale

router = APIRouter()

stripe.api_key = settings.STRIPE_SECRET_KEY

@router.post("/create-checkout-session/{owner_id}/{service_id}")
async def create_checkout_session(
    owner_id: int,
    service_id: int,
    booking_data: BookingCreate,
    db: Session = Depends(get_db),
    request: Request = Request
):
    locale = get_locale(request)
    _ = gettext_for_locale(locale)

    owner = db.query(Owner).filter(Owner.id == owner_id).first()
    service = db.query(Service).filter(Service.id == service_id, Service.owner_id == owner_id).first()

    if not owner or not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Owner or service not found"))

    # Basic validation (more comprehensive validation would be in booking logic)
    if booking_data.start_time < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_("Cannot book in the past"))

    # Check for overlapping bookings (simplified, actual booking logic handles this better)
    existing_booking = db.query(Booking).filter(
        Booking.owner_id == owner_id,
        Booking.service_id == service_id,
        Booking.start_time < booking_data.end_time,
        Booking.end_time > booking_data.start_time,
        Booking.status != BookingStatus.CANCELLED,
        Booking.payment_status == PaymentStatus.PAID # Only consider paid bookings as overlap for now
    ).first()

    if existing_booking:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_("Time slot already booked"))

    try:
        # Create a pending booking first
        db_booking = Booking(
            owner_id=owner.id,
            service_id=service.id,
            customer_name=booking_data.customer_name,
            customer_email=booking_data.customer_email,
            customer_phone=booking_data.customer_phone,
            start_time=booking_data.start_time,
            end_time=booking_data.end_time,
            status=BookingStatus.PENDING, # Initially pending
            payment_status=PaymentStatus.PENDING # Initially pending payment
        )
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        # Construct success and cancel URLs dynamically
        # Use settings.SERVER_NAME to construct absolute URLs
        base_url = settings.SERVER_NAME
        success_url = f"{base_url}/booking-confirmation/{db_booking.id}?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/booking/{owner.business_name.lower().replace(' ', '-')}" # Redirect back to booking page

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": service.name,
                            "description": service.description or "Service booking",
                        },
                        "unit_amount": service.price, # price is in cents
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "booking_id": str(db_booking.id),
                "owner_id": str(owner.id),
                "service_id": str(service.id),
            }
        )
        return {"id": checkout_session.id, "url": checkout_session.url}
    except stripe.error.StripeError as e:
        db.rollback() # Rollback the pending booking if Stripe fails
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback() # Rollback the pending booking if any other error occurs
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    locale = get_locale(request)
    _ = gettext_for_locale(locale)

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
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        booking_id = session.metadata.get("booking_id")

        if booking_id:
            booking = db.query(Booking).filter(Booking.id == int(booking_id)).first()
            if booking:
                booking.payment_status = PaymentStatus.PAID
                booking.status = BookingStatus.CONFIRMED # Confirm booking after payment
                db.add(booking)
                db.commit()
                db.refresh(booking)

                # Send notifications
                owner = db.query(Owner).filter(Owner.id == booking.owner_id).first()
                service = db.query(Service).filter(Service.id == booking.service_id).first()
                if owner and service:
                    await send_booking_confirmation_email(booking, owner, service, locale)
                    await send_owner_booking_notification(booking, owner, service, locale)
                    if owner.phone:
                        await send_whatsapp_message(owner.phone, _("New booking received for {service_name} from {customer_name}").format(service_name=service.name, customer_name=booking.customer_name), locale)
                    if booking.customer_phone:
                        await send_whatsapp_message(booking.customer_phone, _("Your booking for {service_name} is confirmed!").format(service_name=service.name), locale)
            else:
                print(f"Booking with ID {booking_id} not found for payment confirmation.")
        else:
            print("No booking_id found in checkout session metadata.")
    elif event["type"] == "checkout.session.async_payment_failed":
        # Handle failed payments, e.g., update booking status
        session = event["data"]["object"]
        booking_id = session.metadata.get("booking_id")
        if booking_id:
            booking = db.query(Booking).filter(Booking.id == int(booking_id)).first()
            if booking:
                booking.payment_status = PaymentStatus.FAILED
                # Potentially mark booking as cancelled or pending review
                db.add(booking)
                db.commit()
                db.refresh(booking)
        print(f"Async payment failed for session: {session.id}")

    return {"status": "success"}
