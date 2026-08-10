import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from datetime import datetime
import gettext

from . import models
from .config import settings

_ = gettext.gettext

# SendGrid Email Client
sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
FROM_EMAIL = "no-reply@bookslot.app"

# Twilio SMS Client
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
TWILIO_PHONE_NUMBER = settings.TWILIO_PHONE_NUMBER

def send_email(to_email: str, subject: str, html_content: str):
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        response = sendgrid_client.send(message)
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")
        return False

def send_sms(to_phone_number: str, body: str):
    if not to_phone_number:
        print("No phone number provided for SMS.")
        return False
    try:
        message = twilio_client.messages.create(
            to=to_phone_number,
            from_=TWILIO_PHONE_NUMBER,
            body=body
        )
        print(f"SMS sent to {to_phone_number}. SID: {message.sid}")
        return True
    except Exception as e:
        print(f"Error sending SMS to {to_phone_number}: {e}")
        return False

def send_booking_confirmation_to_owner(owner: models.Owner, booking: models.Booking, service: models.Service):
    booking_datetime_str = datetime.combine(booking.date, booking.time).strftime("%Y-%m-%d %H:%M")
    
    subject = _("New Booking Confirmation for {service_name}").format(service_name=service.name)
    html_content = _("""
        <p>Dear {owner_name},</p>
        <p>You have a new booking!</p>
        <ul>
            <li><strong>Service:</strong> {service_name}</li>
            <li><strong>Date & Time:</strong> {booking_datetime}</li>
            <li><strong>Customer Name:</strong> {customer_name}</li>
            <li><strong>Customer Email:</strong> {customer_email}</li>
            <li><strong>Customer Phone:</strong> {customer_phone}</li>
        </ul>
        <p>Thank you!</p>
    """).format(
        owner_name=owner.name,
        service_name=service.name,
        booking_datetime=booking_datetime_str,
        customer_name=booking.customer_name,
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone if booking.customer_phone else _("N/A")
    )
    
    send_email(owner.email, subject, html_content)
    if owner.phone:
        sms_body = _("New booking for {service_name} on {booking_datetime} by {customer_name}. Email: {customer_email}, Phone: {customer_phone}").format(
            service_name=service.name,
            booking_datetime=booking_datetime_str,
            customer_name=booking.customer_name,
            customer_email=booking.customer_email,
            customer_phone=booking.customer_phone if booking.customer_phone else _("N/A")
        )
        send_sms(owner.phone, sms_body)

def send_booking_confirmation_to_customer(booking: models.Booking, service: models.Service):
    booking_datetime_str = datetime.combine(booking.date, booking.time).strftime("%Y-%m-%d %H:%M")

    subject = _("Your Booking Confirmation for {service_name}").format(service_name=service.name)
    html_content = _("""
        <p>Dear {customer_name},</p>
        <p>Your booking has been confirmed!</p>
        <ul>
            <li><strong>Service:</strong> {service_name}</li>
            <li><strong>Date & Time:</strong> {booking_datetime}</li>
        </ul>
        <p>We look forward to seeing you!</p>
    """).format(
        customer_name=booking.customer_name,
        service_name=service.name,
        booking_datetime=booking_datetime_str
    )

    send_email(booking.customer_email, subject, html_content)
    if booking.customer_phone:
        sms_body = _("Your booking for {service_name} on {booking_datetime} has been confirmed!").format(
            service_name=service.name,
            booking_datetime=booking_datetime_str
        )
        send_sms(booking.customer_phone, sms_body)

def send_recurring_booking_notification(booking: models.Booking, service: models.Service, is_owner: bool):
    booking_datetime_str = datetime.combine(booking.date, booking.time).strftime("%Y-%m-%d %H:%M")
    
    if is_owner:
        subject = _("Recurring Booking Alert: {service_name}").format(service_name=service.name)
        html_content = _("""
            <p>Dear {owner_name},</p>
            <p>A recurring booking for {service_name} is scheduled on {booking_datetime} with {customer_name}.</p>
            <p>This is a reminder for your recurring series.</p>
        """).format(
            owner_name="Owner",
            service_name=service.name,
            booking_datetime=booking_datetime_str,
            customer_name=booking.customer_name
        )
    else:
        subject = _("Your Upcoming Recurring Booking for {service_name}").format(service_name=service.name)
        html_content = _("""
            <p>Dear {customer_name},</p>
            <p>This is a reminder for your upcoming recurring booking for {service_name} on {booking_datetime}.</p>
            <p>We look forward to seeing you!</p>
        """).format(
            customer_name=booking.customer_name,
            service_name=service.name,
            booking_datetime=booking_datetime_str
        )
        send_email(booking.customer_email, subject, html_content)
        if booking.customer_phone:
            sms_body = _("Reminder: Your recurring booking for {service_name} is on {booking_datetime}!").format(
                service_name=service.name,
                booking_datetime=booking_datetime_str
            )
            send_sms(booking.customer_phone, sms_body)
