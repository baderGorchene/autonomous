from twilio.rest import Client
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To
from datetime import date, time
from typing import Optional

from .config import settings
from . import models

# Twilio Client
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

# SendGrid Client
sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)

def send_sms_notification(to_phone_number: str, message: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_PHONE_NUMBER:
        print("Twilio credentials not configured. SMS not sent.")
        return
    try:
        message = twilio_client.messages.create(
            to=to_phone_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            body=message
        )
        print(f"SMS sent: {message.sid}")
    except Exception as e:
        print(f"Error sending SMS: {e}")

def send_email_notification(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        print("SendGrid API key not configured. Email not sent.")
        return
    try:
        from_email = Email("no-reply@bookslot.app") # Replace with your verified sender
        to_email_obj = To(to_email)
        message = Mail(from_email, to_email_obj, subject, html_content=html_content)
        response = sg.send(message)
        print(f"Email sent. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email: {e}")

def send_owner_booking_notification(
    owner: models.Owner,
    service: models.Service,
    booking_date: date,
    booking_time: time,
    customer: models.Customer # NEW: customer object
):
    subject = f"New Booking for {service.name}!"
    html_content = f"""
    <p>Dear {owner.name},</p>
    <p>You have a new booking for your service: <strong>{service.name}</strong>.</p>
    <p>Details:</p>
    <ul>
        <li>Date: {booking_date.strftime('%Y-%m-%d')}</li>
        <li>Time: {booking_time.strftime('%H:%M')}</li>
        <li>Customer Name: {customer.name}</li>
        <li>Customer Email: {customer.email or 'N/A'}</li>
        <li>Customer Phone: {customer.phone_number or 'N/A'}</li>
    </ul>
    <p>Thank you!</p>
    """
    if owner.email:
        send_email_notification(owner.email, subject, html_content)
    if owner.phone_number:
        sms_message = f"New booking for {service.name} on {booking_date.strftime('%Y-%m-%d')} at {booking_time.strftime('%H:%M')} by {customer.name}."
        send_sms_notification(owner.phone_number, sms_message)

def send_customer_booking_confirmation(
    owner: models.Owner,
    service: models.Service,
    booking_date: date,
    booking_time: time,
    customer: models.Customer # NEW: customer object
):
    subject = f"Your Booking Confirmation for {service.name} with {owner.name}"
    html_content = f"""
    <p>Dear {customer.name},</p>
    <p>Your booking for <strong>{service.name}</strong> with {owner.name} has been confirmed!</p>
    <p>Details:</p>
    <ul>
        <li>Service: {service.name}</li>
        <li>Date: {booking_date.strftime('%Y-%m-%d')}</li>
        <li>Time: {booking_time.strftime('%H:%M')}</li>
        <li>Owner Contact: {owner.email} {f' / {owner.phone_number}' if owner.phone_number else ''}</li>
    </ul>
    <p>We look forward to seeing you!</p>
    """
    if customer.email:
        send_email_notification(customer.email, subject, html_content)
    if customer.phone_number:
        sms_message = f"Your booking for {service.name} with {owner.name} on {booking_date.strftime('%Y-%m-%d')} at {booking_time.strftime('%H:%M')} is confirmed."
        send_sms_notification(customer.phone_number, sms_message)
