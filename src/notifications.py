import sendgrid
from sendgrid.helpers.mail import Mail
import twilio.rest
from .config import settings
import logging

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str) -> bool:
    """Sends an email using SendGrid."""
    try:
        message = Mail(
            from_email='noreply@bookslot.app',
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        sendgrid_client = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {getattr(response, 'status_code', 200)}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

send_email = send_email_notification

def send_sms_notification(to_phone_number: str, message_body: str) -> bool:

    """Sends an SMS using Twilio."""
    try:
        client = twilio.rest.Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            to=to_phone_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            body=message_body
        )
        logger.info(f"SMS sent to {to_phone_number}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending SMS to {to_phone_number}: {e}")
        return False

def send_whatsapp_notification(to_phone_number: str, message_body: str) -> bool:
    """Sends a WhatsApp message using Twilio."""
    try:
        from_number = getattr(settings, "TWILIO_WHATSAPP_NUMBER", None)
        if not from_number and hasattr(settings, "model_config") and hasattr(settings.model_config, "model_extra"):
            from_number = settings.model_config.model_extra.get("TWILIO_WHATSAPP_NUMBER")
        if not from_number:
            from_number = "+15017122661"
        if not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"
        to_number = to_phone_number if to_phone_number.startswith("whatsapp:") else f"whatsapp:{to_phone_number}"
        client = twilio.rest.Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            from_=from_number,
            body=message_body,
            to=to_number
        )
        logger.info(f"WhatsApp sent to {to_phone_number}. SID: {getattr(msg, 'sid', None)}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp to {to_phone_number}: {e}")
        return False

async def send_whatsapp_message(to_phone_number: str, message_body: str, locale: str = "en") -> bool:
    return send_whatsapp_notification(to_phone_number, message_body)

def send_booking_confirmation(booking, service=None, owner=None, **kwargs):
    owner_email = getattr(owner, "email", kwargs.get("owner_email"))
    owner_phone = getattr(owner, "phone", kwargs.get("owner_phone"))
    cust_email = getattr(booking, "customer_email", kwargs.get("customer_email"))
    cust_phone = getattr(booking, "customer_phone", kwargs.get("customer_phone"))
    svc_name = getattr(service, "name", kwargs.get("service_name", "Service"))
    date_val = getattr(booking, "date", kwargs.get("date", ""))
    time_val = getattr(booking, "time", kwargs.get("time", ""))
    cust_name = getattr(booking, "customer_name", kwargs.get("customer_name", "Customer"))

    if owner_email:
        owner_subject = f"New Booking for {svc_name} from {cust_name}"
        owner_html = f"<h1>New Booking!</h1><p>{cust_name} booked {svc_name} on {date_val} at {time_val}</p>"
        send_email_notification(owner_email, owner_subject, owner_html)
    if owner_phone:
        owner_sms = f"New booking for {svc_name} on {date_val} at {time_val} by {cust_name}."
        send_sms_notification(owner_phone, owner_sms)
        send_whatsapp_notification(owner_phone, owner_sms)

    if cust_email:
        cust_subject = f"Your Booking Confirmation for {svc_name}"
        cust_html = f"<h1>Booking Confirmed!</h1><p>Dear {cust_name}, your booking for {svc_name} on {date_val} at {time_val} is confirmed.</p>"
        send_email_notification(cust_email, cust_subject, cust_html)
    if cust_phone:
        cust_sms = f"Your booking for {svc_name} on {date_val} at {time_val} is confirmed. See you then!"
        send_sms_notification(cust_phone, cust_sms)
        send_whatsapp_notification(cust_phone, cust_sms)
    return True

def send_booking_confirmation_emails(owner, booking, service):
    return send_booking_confirmation(booking=booking, service=service, owner=owner)

def send_booking_confirmation_sms(owner, booking, service):
    return send_booking_confirmation(booking=booking, service=service, owner=owner)

def send_booking_confirmation_email(booking, service, customer):
    return send_booking_confirmation(booking=booking, service=service, owner=None)

def send_owner_booking_notification(booking, service, owner):
    return send_booking_confirmation(booking=booking, service=service, owner=owner)

async def send_booking_notification(owner_email_or_booking=None, owner_phone=None, booking_details=None, business_name: str = "BookSlot", **kwargs):
    if owner_email_or_booking and not isinstance(owner_email_or_booking, str):
        return send_booking_confirmation(booking=owner_email_or_booking, service=owner_phone, owner=booking_details)

    import httpx, os, inspect
    from datetime import datetime

    owner_email = str(owner_email_or_booking or "")
    phone = str(owner_phone or "")
    details = booking_details or {}
    customer = details.get("customer") or details.get("customer_name") or "Customer"
    time_val = details.get("time") or details.get("datetime") or ""
    if isinstance(time_val, datetime):
        time_val = time_val.strftime('%Y-%m-%d %H:%M')

    subject = f"New Booking for {business_name}"
    content = f"New booking from {customer} at {time_val}"
    sendgrid_key = getattr(settings, "SENDGRID_API_KEY", "") or os.getenv("SENDGRID_API_KEY", "")

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {sendgrid_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "personalizations": [{"to": [{"email": owner_email}]}],
                    "from": {"email": "bookings@bookslot.app", "name": "BookSlot"},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": content}]
                }
            )
        except Exception as e:
            logger.error(f"SendGrid error in send_booking_notification: {e}")

    if phone:
        try:
            res = send_whatsapp_notification(phone, content)
            if inspect.isawaitable(res):
                await res
        except Exception:
            pass
    return True

async def send_customer_confirmation_email(customer_email: str, booking_details: dict, business_name: str = "BookSlot"):
    import httpx, os
    sendgrid_key = getattr(settings, "SENDGRID_API_KEY", "") or os.getenv("SENDGRID_API_KEY", "")
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {sendgrid_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "personalizations": [{"to": [{"email": customer_email}]}],
                    "from": {"email": "noreply@bookslot.app", "name": "BookSlot"},
                    "subject": f"Your booking confirmation with {business_name}",
                    "content": [{"type": "text/plain", "value": f"Booking confirmed with {business_name}"}]
                }
            )
        except Exception:
            pass
    return True