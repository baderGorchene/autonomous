import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings
import logging

logger = logging.getLogger(__name__)

def send_email_confirmation_to_customer(customer_email: str, owner_name: str, service_name: str, booking_date: str, booking_time: str, owner_email: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid API key not set. Skipping customer email.")
        return

    message = Mail(
        from_email=owner_email, # Use owner's email as from_email for better branding/replies
        to_emails=customer_email,
        subject=f"Booking Confirmation with {owner_name} for {service_name}",
        html_content=f"""
        <p>Dear {customer_email},</p>
        <p>Your booking with {owner_name} for {service_name} on {booking_date} at {booking_time} has been confirmed.</p>
        <p>We look forward to seeing you!</p>
        <p>Best regards,</p>
        <p>{owner_name}</p>
        """
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Customer email sent. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending customer email: {e}")

def send_email_notification_to_owner(owner_email: str, customer_name: str, customer_email: str, service_name: str, booking_date: str, booking_time: str, owner_name: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SendGrid API key not set. Skipping owner email notification.")
        return

    message = Mail(
        from_email="noreply@bookslot.app", # Generic no-reply for owner notification
        to_emails=owner_email,
        subject=f"New Booking for {service_name} from {customer_name}",
        html_content=f"""
        <p>Dear {owner_name},</p>
        <p>You have a new booking!</p>
        <ul>
            <li>Service: {service_name}</li>
            <li>Date: {booking_date}</li>
            <li>Time: {booking_time}</li>
            <li>Customer Name: {customer_name}</li>
            <li>Customer Email: {customer_email}</li>
        </ul>
        <p>Please check your dashboard for more details.</p>
        """
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Owner email notification sent. Status Code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending owner email notification: {e}")

def send_whatsapp_notification_to_owner(owner_phone: str, customer_name: str, service_name: str, booking_date: str, booking_time: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not fully set. Skipping WhatsApp notification.")
        return

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    body = f"New booking for {service_name} from {customer_name} on {booking_date} at {booking_time}."
    try:
        message = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            to=f"whatsapp:{owner_phone}",
            body=body
        )
        logger.info(f"WhatsApp message sent. SID: {message.sid}")
    except Exception as e:
        logger.error(f"Error sending WhatsApp notification: {e}")