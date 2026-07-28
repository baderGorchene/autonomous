import os
import httpx
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings

sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)

twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
TWILIO_WHATSAPP_NUMBER = settings.TWILIO_WHATSAPP_NUMBER

async def send_email(to_email: str, subject: str, html_content: str):
    message = Mail(
        from_email='no-reply@bookslot.app',
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        response = sendgrid_client.send(message)
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")

async def send_whatsapp_message(to_phone_number: str, body: str):
    try:
        if not to_phone_number.startswith("whatsapp:"):
            to_phone_number = f"whatsapp:{to_phone_number}"

        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=body,
            to=to_phone_number
        )
        print(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone_number}: {e}")

async def send_booking_confirmation_email_to_customer(
    customer_email: str, business_name: str, service_name: str, booking_datetime_str: str
):
    subject = f"Your booking with {business_name} is confirmed!"
    html_content = f"""
    <p>Dear Customer,</p>
    <p>Your booking for <strong>{service_name}</strong> with <strong>{business_name}</strong> on <strong>{booking_datetime_str}</strong> has been successfully confirmed.</p>
    <p>We look forward to seeing you!</p>
    <p>Best regards,<br>{business_name} Team</p>
    """
    await send_email(customer_email, subject, html_content)

async def send_new_booking_notification_to_owner(
    owner_email: str, owner_phone: str, business_name: str,
    customer_name: str, customer_email: str, customer_phone: str,
    service_name: str, booking_datetime_str: str
):
    email_subject = f"New booking for {business_name}!"
    email_html_content = f"""
    <p>Hello {business_name} Team,</p>
    <p>You have a new booking!</p>
    <ul>
        <li><strong>Service:</strong> {service_name}</li>
        <li><strong>When:</strong> {booking_datetime_str}</li>
        <li><strong>Customer Name:</strong> {customer_name}</li>
        <li><strong>Customer Email:</strong> {customer_email}</li>
        <li><strong>Customer Phone:</strong> {customer_phone}</li>
    </ul>
    <p>Please check your dashboard for more details.</p>
    """
    await send_email(owner_email, email_subject, email_html_content)

    whatsapp_body = f"New booking for {business_name}!\nService: {service_name}\nWhen: {booking_datetime_str}\nCustomer: {customer_name} ({customer_phone})"
    await send_whatsapp_message(owner_phone, whatsapp_body)

async def generate_ai_response(prompt: str) -> str:
    if not settings.GEMINI_API_KEY:
        print("GEMINI_API_KEY not set. Skipping AI response generation.")
        return "AI capabilities are not enabled."
    
    print(f"Gemini API call with prompt: {prompt}")
    return "This is a dummy AI response. Please set up Gemini API for actual functionality."