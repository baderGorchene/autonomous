import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
import logging

from ..config import settings
from ..schemas import Booking

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str):
    try:
        message = Mail(
            from_email='no-reply@bookslot.app',
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")

def send_whatsapp_message(to_phone_number: str, message_body: str):
    try:
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        client = Client(account_sid, auth_token)

        message = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            body=message_body,
            to=f"whatsapp:{to_phone_number}"
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")

def send_booking_confirmation(
    owner_email: str,
    owner_phone: Optional[str],
    customer_email: str,
    customer_phone: Optional[str],
    booking: Booking,
    owner_name: str,
    business_name: str
):
    booking_time_str = booking.datetime.strftime('%Y-%m-%d %H:%M')
    
    customer_email_subject = f"Your BookSlot Appointment with {business_name} is Confirmed!"
    customer_email_html = f"""
    <html>
    <body>
        <p>Dear {booking.customer_name},</p>
        <p>Your appointment for <strong>{booking.service_name}</strong> with <strong>{business_name}</strong> has been confirmed.</p>
        <p><strong>Date & Time:</strong> {booking_time_str}</p>
        <p>We look forward to seeing you!</p>
        <p>Best regards,</p>
        <p>{business_name}</p>
    </body>
    </html>
    """
    send_email(customer_email, customer_email_subject, customer_email_html)

    if customer_phone:
        customer_whatsapp_message = (
            f"Hi {booking.customer_name},\n"
            f"Your booking for {booking.service_name} with {business_name} on {booking_time_str} is confirmed.\n"
            f"See you then!"
        )
        send_whatsapp_message(customer_phone, customer_whatsapp_message)

    owner_email_subject = f"New BookSlot Booking for {business_name}!"
    owner_email_html = f"""
    <html>
    <body>
        <p>Dear {owner_name},</p>
        <p>A new booking has been made for your business, <strong>{business_name}</strong>:</p>
        <ul>
            <li><strong>Service:</strong> {booking.service_name}</li>
            <li><strong>Date & Time:</strong> {booking_time_str}</li>
            <li><strong>Customer Name:</strong> {booking.customer_name}</li>
            <li><strong>Customer Email:</strong> {booking.customer_email}</li>
            <li><strong>Customer Phone:</strong> {booking.customer_phone or 'N/A'}</li>
        </ul>
        <p>Please check your dashboard for more details.</p>
        <p>Best regards,</p>
        <p>BookSlot Team</p>
    </body>
    </html>
    """
    send_email(owner_email, owner_email_subject, owner_email_html)

    if owner_phone:
        owner_whatsapp_message = (
            f"New booking for {business_name}:\n"
            f"Service: {booking.service_name}\n"
            f"Date & Time: {booking_time_str}\n"
            f"Customer: {booking.customer_name} ({booking.customer_phone or booking.customer_email})\n"
            f"Check dashboard for details."
        )
        send_whatsapp_message(owner_phone, owner_whatsapp_message)
