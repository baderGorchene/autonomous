from typing import List
from .config import settings

def send_email(to_email: str, subject: str, body: str):
    if settings.SENDGRID_API_KEY:
        # Placeholder for SendGrid integration
        # from sendgrid import SendGridAPIClient
        # from sendgrid.helpers.mail import Mail
        # message = Mail(from_email='no-reply@bookslot.app', to_emails=to_email, subject=subject, html_content=body)
        # try:
        #     sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        #     response = sg.send(message)
        #     print(f"Email sent via SendGrid: {response.status_code}")
        # except Exception as e:
        #     print(f"Error sending email via SendGrid: {e}")
        pass
    else:
        print(f"EMAIL (to: {to_email}, subject: {subject}): {body}")

def send_whatsapp_message(to_phone_number: str, message_body: str):
    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_NUMBER:
        # Placeholder for Twilio integration
        # from twilio.rest import Client
        # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        # try:
        #     message = client.messages.create(
        #         from_=settings.TWILIO_WHATSAPP_NUMBER,
        #         body=message_body,
        #         to=f'whatsapp:{to_phone_number}'
        #     )
        #     print(f"WhatsApp message sent via Twilio: {message.sid}")
        # except Exception as e:
        #     print(f"Error sending WhatsApp message via Twilio: {e}")
        pass
    else:
        print(f"WHATSAPP (to: {to_phone_number}): {message_body}")

def notify_booking_confirmation(owner_email: str, owner_phone: str, customer_email: str, customer_phone: str, booking_details: dict, owner_locale: str = "en"):
    # Simplified notification logic
    owner_subject = f"New Booking: {booking_details['service_name']}"
    owner_body = f"A new booking has been made for {booking_details['service_name']} on {booking_details['date']} at {booking_details['time']} by {booking_details['customer_name']} (Email: {customer_email}, Phone: {customer_phone})."
    send_email(owner_email, owner_subject, owner_body)
    send_whatsapp_message(owner_phone, owner_body)

    customer_subject = f"Your Booking Confirmation: {booking_details['service_name']}"
    customer_body = f"Your booking for {booking_details['service_name']} on {booking_details['date']} at {booking_details['time']} has been confirmed. Thank you!"
    send_email(customer_email, customer_subject, customer_body)
    send_whatsapp_message(customer_phone, customer_body)