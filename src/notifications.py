import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings

def send_email(to_email: str, subject: str, html_content: str):
    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        print(f"SendGrid Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        print(f"Error sending email via SendGrid: {e}")
        return False

def send_whatsapp_message(to_phone_number: str, message_body: str):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone_number}'
        )
        print(f"Twilio WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
        return True
    except Exception as e:
        print(f"Error sending WhatsApp message via Twilio: {e}")
        return False

# Placeholder for email templates
def get_owner_booking_confirmation_email_content(owner_name: str, booking_details: dict):
    return f"""
    <html>
    <body>
        <h1>New Booking for {owner_name}!</h1>
        <p>You have a new booking from {booking_details['customer_name']}.</p>
        <p>Service: {booking_details['service_name']}</p>
        <p>Date: {booking_details['booking_date']}</p>
        <p>Time: {booking_details['booking_time']}</p>
        <p>Customer Email: {booking_details['customer_email']}</p>
        <p>Customer Phone: {booking_details.get('customer_phone', 'N/A')}</p>
        <p>Thank you for using BookSlot!</p>
    </body>
    </html>
    """

def get_customer_booking_confirmation_email_content(customer_name: str, business_name: str, booking_details: dict):
    return f"""
    <html>
    <body>
        <h1>Booking Confirmation for {customer_name}!</h1>
        <p>Your booking with {business_name} has been confirmed.</p>
        <p>Service: {booking_details['service_name']}</p>
        <p>Date: {booking_details['booking_date']}</p>
        <p>Time: {booking_details['booking_time']}</p>
        <p>Thank you for choosing {business_name}!</p>
    </body>
    </html>
    """

def get_owner_booking_confirmation_whatsapp_content(owner_name: str, booking_details: dict):
    return (
        f"Hello {owner_name}, you have a new booking!\n"
        f"Customer: {booking_details['customer_name']}\n"
        f"Service: {booking_details['service_name']}\n"
        f"Date: {booking_details['booking_date']}\n"
        f"Time: {booking_details['booking_time']}\n"
        f"Customer Email: {booking_details['customer_email']}\n"
        f"Customer Phone: {booking_details.get('customer_phone', 'N/A')}\n"
        f"BookSlot App."
    )

def get_customer_booking_confirmation_whatsapp_content(customer_name: str, business_name: str, booking_details: dict):
    return (
        f"Hello {customer_name}, your booking with {business_name} is confirmed!\n"
        f"Service: {booking_details['service_name']}\n"
        f"Date: {booking_details['booking_date']}\n"
        f"Time: {booking_details['booking_time']}\n"
        f"Thank you for choosing {business_name}!"
    )
