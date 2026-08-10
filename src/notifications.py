from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
from typing import Dict, Any

def send_email(to_email: str, subject: str, html_content: str):
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

def send_sms(to_phone_number: str, body: str):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            to=to_phone_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            body=body
        )
        print(f"SMS sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending SMS to {to_phone_number}: {e}")

def send_booking_confirmation_email(booking_details: Dict[str, Any], owner_email: str, customer_email: str, is_owner: bool):
    subject = f"Booking Confirmation for {booking_details['service_name']}"
    if is_owner:
        html_content = f"<p>New booking for your service: {booking_details['service_name']}.</p><p>Customer: {booking_details['customer_name']} ({booking_details['customer_email']}).</p><p>Date: {booking_details['date']}. Time: {booking_details['time']}.</p>"
        send_email(owner_email, subject, html_content)
    else:
        html_content = f"<p>Your booking for {booking_details['service_name']} is confirmed.</p><p>Date: {booking_details['date']}. Time: {booking_details['time']}.</p>"
        send_email(customer_email, subject, html_content)

def send_booking_confirmation_sms(booking_details: Dict[str, Any], owner_phone: str, customer_phone: str, is_owner: bool):
    if is_owner:
        body = f"New booking for {booking_details['service_name']}. Customer: {booking_details['customer_name']}. Date: {booking_details['date']}, Time: {booking_details['time']}."
        send_sms(owner_phone, body)
    else:
        body = f"Your booking for {booking_details['service_name']} is confirmed. Date: {booking_details['date']}, Time: {booking_details['time']}."
        send_sms(customer_phone, body)