from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
from . import models
from typing import List

# SendGrid Email Client
sg = SendGridAPIClient(settings.SENDGRID_API_KEY)

# Twilio SMS Client
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

def send_email(to_email: str, subject: str, html_content: str):
    message = Mail(
        from_email='no-reply@bookslot.app', # TODO: Use a verified sender email
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        response = sg.send(message)
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")

def send_sms(to_phone_number: str, body: str):
    if not settings.TWILIO_PHONE_NUMBER or not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        print("Twilio credentials not fully configured. Skipping SMS.")
        return

    try:
        message = twilio_client.messages.create(
            to=to_phone_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            body=body
        )
        print(f"SMS sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending SMS to {to_phone_number}: {e}")

def send_booking_confirmation_emails(owner: models.Owner, service: models.Service, booking: models.Booking, is_recurring: bool = False):
    # Customer Email
    customer_subject = f"Booking Confirmation for {service.name}"
    recurrence_info = " (Recurring Booking)" if is_recurring else ""
    customer_html = f"""
    <p>Hi {booking.customer_name},</p>
    <p>Your booking for <b>{service.name}</b> with <b>{owner.name}</b> on <b>{booking.date.strftime('%Y-%m-%d')}</b> at <b>{booking.time.strftime('%H:%M')}</b> has been confirmed{recurrence_info}.</p>
    <p>Service: {service.name}</p>
    <p>Duration: {service.duration_minutes} minutes</p>
    <p>Price: ${service.price / 100:.2f}</p>
    <p>Owner's Contact: {owner.phone or owner.email}</p>
    <p>Thank you!</p>
    """
    send_email(booking.customer_email, customer_subject, customer_html)
    if booking.customer_phone:
        send_sms(booking.customer_phone, f"Your booking for {service.name} with {owner.name} on {booking.date.strftime('%Y-%m-%d')} at {booking.time.strftime('%H:%M')} is confirmed{recurrence_info}.")


    # Owner Email
    owner_subject = f"New Booking for {service.name}"
    owner_html = f"""
    <p>Hello {owner.name},</p>
    <p>You have a new booking for <b>{service.name}</b> on <b>{booking.date.strftime('%Y-%m-%d')}</b> at <b>{booking.time.strftime('%H:%M')}</b>{recurrence_info}.</p>
    <p>Customer Name: {booking.customer_name}</p>
    <p>Customer Email: {booking.customer_email}</p>
    <p>Customer Phone: {booking.customer_phone or 'N/A'}</p>
    <p>Service: {service.name}</p>
    <p>Duration: {service.duration_minutes} minutes</p>
    <p>Price: ${service.price / 100:.2f}</p>
    """
    send_email(owner.email, owner_subject, owner_html)
    if owner.phone:
        send_sms(owner.phone, f"New booking for {service.name} on {booking.date.strftime('%Y-%m-%d')} at {booking.time.strftime('%H:%M')} by {booking.customer_name}{recurrence_info}.")
