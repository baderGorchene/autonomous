from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging
from src.config import settings
from src import schemas, models
import json

logger = logging.getLogger(__name__)

# Email Templates (simplified for now)
def get_owner_booking_email_content(owner_name: str, business_name: str, booking: schemas.Booking, service_details: dict):
    return f"""
    Dear {owner_name},

    You have a new booking for your service: {booking.service_name} at {business_name}.

    Booking Details:
    Customer Name: {booking.customer_name}
    Customer Email: {booking.customer_email}
    Customer Phone: {booking.customer_phone if booking.customer_phone else 'N/A'}
    Service: {booking.service_name} (Duration: {service_details.get('duration_minutes', 'N/A')} mins, Price: ${service_details.get('price', 'N/A')})
    Date: {booking.booking_date.strftime('%Y-%m-%d')}
    Time: {booking.booking_time}

    Thank you,
    BookSlot Team
    """

def get_customer_booking_email_content(customer_name: str, business_name: str, booking: schemas.Booking, owner_phone: str, service_details: dict):
    return f"""
    Dear {customer_name},

    Your booking for {booking.service_name} at {business_name} has been confirmed!

    Booking Details:
    Service: {booking.service_name} (Duration: {service_details.get('duration_minutes', 'N/A')} mins, Price: ${service_details.get('price', 'N/A')})
    Date: {booking.booking_date.strftime('%Y-%m-%d')}
    Time: {booking.booking_time}

    If you need to contact us, please call {owner_phone}.

    Thank you for using BookSlot!
    """

def send_email_notification(to_email: str, subject: str, content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid API key not configured. Skipping email notification.")
        return

    message = Mail(
        from_email='noreply@bookslot.app', # Replace with your verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email} with status code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")

def send_whatsapp_notification(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not configured. Skipping WhatsApp notification.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone_number}'
        )
        logger.info(f"WhatsApp message sent to {to_phone_number} with SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")

def notify_new_booking(db_owner: models.Owner, booking: schemas.BookingCreate):
    # Determine the service details for the notification
    services = json.loads(db_owner.services_json)
    service_details = next((s for s in services if s['name'] == booking.service_name), {})

    # Notify owner via email
    owner_subject = f"New Booking for {booking.service_name} at {db_owner.business_name}"
    owner_content = get_owner_booking_email_content(db_owner.name, db_owner.business_name, booking, service_details)
    send_email_notification(db_owner.email, owner_subject, owner_content)

    # Notify customer via email
    customer_subject = f"Your Booking Confirmation for {db_owner.business_name}"
    customer_content = get_customer_booking_email_content(booking.customer_name, db_owner.business_name, booking, db_owner.phone, service_details)
    send_email_notification(booking.customer_email, customer_subject, customer_content)

    # Optionally notify owner via WhatsApp
    if db_owner.phone:
        whatsapp_message = f"New booking for {db_owner.business_name}!\n" \
                           f"Service: {booking.service_name}\n" \
                           f"Date: {booking.booking_date.strftime('%Y-%m-%d')}\n" \
                           f"Time: {booking.booking_time}\n" \
                           f"Customer: {booking.customer_name} ({booking.customer_phone if booking.customer_phone else booking.customer_email})"
        send_whatsapp_notification(db_owner.phone, whatsapp_message)
