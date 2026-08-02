import logging
from src.config import settings
# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail
# from twilio.rest import Client

logger = logging.getLogger(__name__)

def send_booking_confirmation_email(owner_email: str, customer_email: str, booking_details: dict):
    # This is a placeholder for actual email sending logic
    # In a real app, you'd use SendGrid or similar here
    logger.info(f"Sending email confirmation to owner {owner_email} and customer {customer_email} for booking: {booking_details}")
    # message = Mail(
    #     from_email='no-reply@bookslot.app',
    #     to_emails=[owner_email, customer_email],
    #     subject='Booking Confirmation',
    #     html_content=f'<strong>Your booking details:</strong><br>{booking_details}'
    # )
    # try:
    #     sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
    #     response = sendgrid_client.send(message)
    #     logger.info(f"Email sent with status code: {response.status_code}")
    # except Exception as e:
    #     logger.error(f"Error sending email: {e}")

def send_whatsapp_notification(phone_number: str, message: str):
    # This is a placeholder for actual WhatsApp sending logic
    # In a real app, you'd use Twilio or similar here
    logger.info(f"Sending WhatsApp message to {phone_number}: {message}")
    # try:
    #     client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    #     message = client.messages.create(
    #         from_=settings.TWILIO_WHATSAPP_NUMBER,
    #         body=message,
    #         to=f'whatsapp:{phone_number}'
    #     )
    #     logger.info(f"WhatsApp message sent with SID: {message.sid}")
    # except Exception as e:
    #     logger.error(f"Error sending WhatsApp message: {e}")