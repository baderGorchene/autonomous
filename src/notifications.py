from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        print(f"Skipping email to {to_email} (no SendGrid API Key): {subject}")
        return

    message = Mail(
        from_email='noreply@bookslot.app',
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")

def send_whatsapp_message(to_phone: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        print(f"Skipping WhatsApp to {to_phone} (Twilio not configured): {message_body}")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=message_body,
            to=f'whatsapp:{to_phone}'
        )
        print(f"WhatsApp message sent to {to_phone}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone}: {e}")

def send_booking_confirmation_email(customer_email: str, owner_name: str, service_name: str, booking_time: str, locale: str = 'en'):
    # In a real app, this would use i18n and proper templating
    subject = f"Your booking with {owner_name} for {service_name} is confirmed!"
    html_content = f"<p>Hi {customer_email.split('@')[0]},</p> <p>Your booking for <b>{service_name}</b> with <b>{owner_name}</b> on <b>{booking_time}</b> has been confirmed.</p> <p>Thank you!</p>"
    send_email(customer_email, subject, html_content)

def send_owner_notification_email(owner_email: str, customer_name: str, service_name: str, booking_time: str, customer_contact: str, locale: str = 'en'):
    # In a real app, this would use i18n and proper templating
    subject = f"New Booking for {service_name} from {customer_name}"
    html_content = f"<p>Hi,</p> <p>You have a new booking for <b>{service_name}</b> on <b>{booking_time}</b>.</p> <p>Customer: {customer_name}</p> <p>Contact: {customer_contact}</p>"
    send_email(owner_email, subject, html_content)

def send_owner_notification_whatsapp(owner_phone: str, customer_name: str, service_name: str, booking_time: str, customer_contact: str, locale: str = 'en'):
    # In a real app, this would use i18n and proper templating
    message_body = f"New Booking: {service_name} on {booking_time}. Customer: {customer_name}, Contact: {customer_contact}"
    send_whatsapp_message(owner_phone, message_body)
