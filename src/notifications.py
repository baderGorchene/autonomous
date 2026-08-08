from typing import Dict, Optional
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        print(f"SendGrid API Key not set. Skipping email to {to_email} with subject '{subject}'.")
        return

    message = Mail(
        from_email=('noreply@bookslot.app', 'BookSlot'),
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

def send_whatsapp_notification(to_phone_number: Optional[str], booking_details: Dict):
    if not to_phone_number or not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        print(f"Twilio credentials or recipient phone number not fully set. Skipping WhatsApp notification to {to_phone_number}.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        message_body = (
            f"New booking for {booking_details['service_name']}!\n"
            f"Customer: {booking_details['customer_name']} ({booking_details['customer_email']})\n"
            f"Time: {booking_details['start_time']}\n"
            f"Price: {booking_details['price']}"
        )

        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=message_body,
            to=f"whatsapp:{to_phone_number}"
        )
        print(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp notification to {to_phone_number}: {e}")

def send_booking_confirmation_email(owner_email: str, customer_email: str, booking_details: Dict):
    owner_subject = f"New Booking: {booking_details['service_name']} on {booking_details['start_time']}"
    owner_html = f"""
    <p>Dear {booking_details['owner_name']},</p>
    <p>You have a new booking!</p>
    <ul>
        <li>Service: {booking_details['service_name']}</li>
        <li>Customer: {booking_details['customer_name']} ({booking_details['customer_email']}{f', {booking_details["customer_phone"]}' if booking_details['customer_phone'] else ''})</li>
        <li>Time: {booking_details['start_time']} - {booking_details['end_time']}</li>
        <li>Price: {booking_details['price']}</li>
    </ul>
    <p>Thank you!</p>
    """
    send_email(owner_email, owner_subject, owner_html)

    customer_subject = f"Your Booking for {booking_details['service_name']} is Confirmed!"
    customer_html = f"""
    <p>Dear {booking_details['customer_name']},</p>
    <p>Your booking for <b>{booking_details['service_name']}</b> with {booking_details['owner_name']} has been confirmed.</p>
    <ul>
        <li>Time: {booking_details['start_time']} - {booking_details['end_time']}</li>
        <li>Price: {booking_details['price']}</li>
        <li>Location/Details: (provided by owner)</li>
    </ul>
    <p>We look forward to seeing you!</p>
    """
    send_email(customer_email, customer_subject, customer_html)

def send_premium_confirmation_email(owner_email: str, owner_name: str):
    subject = "Welcome to BookSlot Premium!"
    html_content = f"""
    <p>Dear {owner_name},</p>
    <p>Congratulations! You have successfully upgraded to BookSlot Premium.</p>
    <p>You now have access to unlimited bookings and all premium features.</p>
    <p>Thank you for being a valued BookSlot customer!</p>
    <p>Best regards,</p>
    <p>The BookSlot Team</p>
    """
    send_email(owner_email, subject, html_content)
