import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from datetime import datetime
from typing import Optional

from . import models
from .config import settings

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        print(f"SendGrid API key not configured. Skipping email to {to_email}: {subject}")
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
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")

def send_sms(to_phone_number: str, body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_PHONE_NUMBER:
        print(f"Twilio not configured. Skipping SMS to {to_phone_number}: {body}")
        return

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

def send_booking_confirmation(owner: models.Owner, service: models.Service, booking: models.Booking):
    # Customer email confirmation
    customer_subject = f"Your booking for {service.name} with {owner.name} is confirmed!"
    customer_body = f"""
    <html>
    <body>
        <p>Dear {booking.customer_name},</p>
        <p>Your booking for <strong>{service.name}</strong> with <strong>{owner.name}</strong> has been confirmed.</p>
        <p><strong>Date:</strong> {booking.date.strftime('%Y-%m-%d')}</p>
        <p><strong>Time:</strong> {booking.time.strftime('%H:%M')}</p>
        <p><strong>Service:</strong> {service.name}</p>
        <p><strong>Duration:</strong> {service.duration_minutes} minutes</p>
        <p><strong>Price:</strong> {service.price} {service.currency}</p>
        {"<p>This is a recurring booking ending on: " + booking.recurrence_end_date.strftime('%Y-%m-%d') + "</p>" if booking.is_recurring and booking.recurrence_end_date else ""}
        <p>Thank you for choosing {owner.name}!</p>
        <p>Best regards,</p>
        <p>BookSlot Team</p>
    </body>
    </html>
    """
    send_email(booking.customer_email, customer_subject, customer_body)
    # send_sms(booking.customer_phone, f"Your booking for {service.name} with {owner.name} on {booking.date.strftime('%Y-%m-%d')} at {booking.time.strftime('%H:%M')} is confirmed!")


def send_booking_notification_to_owner(owner: models.Owner, service: models.Service, booking: models.Booking):
    # Owner email notification
    owner_subject = f"New booking for {service.name} from {booking.customer_name}"
    owner_body = f"""
    <html>
    <body>
        <p>Dear {owner.name},</p>
        <p>You have a new booking!</p>
        <p><strong>Customer Name:</strong> {booking.customer_name}</p>
        <p><strong>Customer Email:</strong> {booking.customer_email}</p>
        <p><strong>Customer Phone:</strong> {booking.customer_phone or 'N/A'}</p>
        <p><strong>Service:</strong> {service.name}</p>
        <p><strong>Date:</strong> {booking.date.strftime('%Y-%m-%d')}</p>
        <p><strong>Time:</strong> {booking.time.strftime('%H:%M')}</p>
        <p><strong>Duration:</strong> {service.duration_minutes} minutes</p>
        <p><strong>Price:</strong> {service.price} {service.currency}</p>
        {"<p>This is a recurring booking ending on: " + booking.recurrence_end_date.strftime('%Y-%m-%d') + "</p>" if booking.is_recurring and booking.recurrence_end_date else ""}
        <p>Manage your bookings: [Link to Owner Dashboard]</p>
        <p>Best regards,</p>
        <p>BookSlot Team</p>
    </body>
    </html>
    """
    send_email(owner.email, owner_subject, owner_body)
    # send_sms(owner.phone_number, f"New booking for {service.name} from {booking.customer_name} on {booking.date.strftime('%Y-%m-%d')} at {booking.time.strftime('%H:%M')}. Customer: {booking.customer_phone}")
