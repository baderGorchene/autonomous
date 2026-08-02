import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from typing import Dict, Any
import logging
from .config import settings

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Email notification skipped for %s.", to_email)
        return

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info("Email sent to %s. Status Code: %s", to_email, response.status_code)
        if response.status_code >= 400:
            logger.error("SendGrid email failed for %s. Response body: %s", to_email, response.body)
    except Exception as e:
        logger.error("Error sending email to %s: %s", to_email, e)

def send_whatsapp_notification(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not fully set. WhatsApp notification skipped for %s.", to_phone_number)
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone_number}'
        )
        logger.info("WhatsApp message sent to %s. SID: %s", to_phone_number, message.sid)
    except Exception as e:
        logger.error("Error sending WhatsApp message to %s: %s", to_phone_number, e)

def send_booking_confirmation_email(owner_email: str, customer_email: str, booking_details: Dict[str, Any], owner_name: str, business_name: str):
    # Owner notification
    owner_subject = f"New Booking for {business_name} - {booking_details['service_name']}"
    owner_html = f"""
    <p>Dear {owner_name},</p>
    <p>You have a new booking!</p>
    <p><strong>Service:</strong> {booking_details['service_name']}</p>
    <p><strong>Date:</strong> {booking_details['booking_date'].strftime('%Y-%m-%d')}</p>
    <p><strong>Time:</strong> {booking_details['booking_time']}</p>
    <p><strong>Customer Name:</strong> {booking_details['customer_name']}</p>
    <p><strong>Customer Email:</strong> {booking_details['customer_email']}</p>
    <p><strong>Customer Phone:</strong> {booking_details.get('customer_phone', 'N/A')}</p>
    <p>Please check your dashboard for more details.</p>
    <p>Thank you!</p>
    """
    send_email_notification(owner_email, owner_subject, owner_html)

    # Customer notification
    customer_subject = f"Your Booking Confirmation with {business_name}"
    customer_html = f"""
    <p>Dear {booking_details['customer_name']},</p>
    <p>Your booking with {business_name} has been confirmed!</p>
    <p><strong>Service:</strong> {booking_details['service_name']}</p>
    <p><strong>Date:</strong> {booking_details['booking_date'].strftime('%Y-%m-%d')}</p>
    <p><strong>Time:</strong> {booking_details['booking_time']}</p>
    <p>We look forward to seeing you!</p>
    <p>Thank you!</p>
    """
    send_email_notification(customer_email, customer_subject, customer_html)

def send_owner_whatsapp_notification(owner_phone: str, booking_details: Dict[str, Any], business_name: str):
    message_body = (
        f"New Booking for {business_name}!\n"
        f"Service: {booking_details['service_name']}\n"
        f"Date: {booking_details['booking_date'].strftime('%Y-%m-%d')}\n"
        f"Time: {booking_details['booking_time']}\n"
        f"Customer: {booking_details['customer_name']}\n"
        f"Email: {booking_details['customer_email']}\n"
        f"Phone: {booking_details.get('customer_phone', 'N/A')}"
    )
    send_whatsapp_notification(owner_phone, message_body)
