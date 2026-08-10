import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from typing import Callable

from . import models
from .config import settings

sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)

twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
TWILIO_FROM_NUMBER = settings.TWILIO_PHONE_NUMBER

def send_email(to_email: str, subject: str, html_content: str):
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

def send_sms(to_phone_number: str, body: str):
    if not to_phone_number or not TWILIO_FROM_NUMBER:
        print("Twilio phone numbers not configured. Skipping SMS.")
        return

    try:
        message = twilio_client.messages.create(
            to=to_phone_number,
            from_=TWILIO_FROM_NUMBER,
            body=body
        )
        print(f"SMS sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending SMS to {to_phone_number}: {e}")

def send_booking_confirmation_email(owner: models.Owner, service: models.Service, booking: models.Booking, _=Callable):
    subject = _("New Booking Confirmation for %(service_name)s") % {"service_name": service.name}
    html_content = f"""
    <html>
    <body>
        <p>{_("Hello %(owner_name)s,") % {"owner_name": owner.name}}</p>
        <p>{_("A new booking has been made for your service:")}</p>
        <ul>
            <li><strong>{_("Service:")}</strong> {service.name}</li>
            <li><strong>{_("Date:")}</strong> {booking.date.strftime('%Y-%m-%d')}</li>
            <li><strong>{_("Time:")}</strong> {booking.time.strftime('%H:%M')}</li>
            <li><strong>{_("Customer Name:")}</strong> {booking.customer_name}</li>
            <li><strong>{_("Customer Email:")}</strong> {booking.customer_email}</li>
            <li><strong>{_("Customer Phone:")}</strong> {booking.customer_phone or _("N/A")}</li>
        </ul>
        <p>{_("Thank you,")}<br/>BookSlot Team</p>
    </body>
    </html>
    """
    send_email(owner.email, subject, html_content)

def send_booking_confirmation_email_to_customer(owner: models.Owner, service: models.Service, booking: models.Booking, _=Callable):
    subject = _("Your Booking Confirmation with %(owner_name)s") % {"owner_name": owner.name}
    html_content = f"""
    <html>
    <body>
        <p>{_("Hello %(customer_name)s,") % {"customer_name": booking.customer_name}}</p>
        <p>{_("Your booking with %(owner_name)s has been confirmed:") % {"owner_name": owner.name}}</p>
        <ul>
            <li><strong>{_("Service:")}</strong> {service.name}</li>
            <li><strong>{_("Date:")}</strong> {booking.date.strftime('%Y-%m-%d')}</li>
            <li><strong>{_("Time:")}</strong> {booking.time.strftime('%H:%M')}</li>
            <li><strong>{_("Owner:")}</strong> {owner.name}</li>
            <li><strong>{_("Owner Contact:")}</strong> {owner.email}</li>
        </ul>
        <p>{_("We look forward to seeing you!")}<br/>BookSlot Team</p>
    </body>
    </html>
    """
    send_email(booking.customer_email, subject, html_content)

def send_booking_confirmation_sms(owner: models.Owner, service: models.Service, booking: models.Booking, _=Callable):
    if owner.phone:
        sms_body = _("New booking for %(service_name)s on %(date)s at %(time)s by %(customer_name)s. Email: %(customer_email)s. Phone: %(customer_phone)s.") % {
            "service_name": service.name,
            "date": booking.date.strftime('%Y-%m-%d'),
            "time": booking.time.strftime('%H:%M'),
            "customer_name": booking.customer_name,
            "customer_email": booking.customer_email,
            "customer_phone": booking.customer_phone or _("N/A")
        }
        send_sms(owner.phone, sms_body)

    if booking.customer_phone:
        sms_body_customer = _("Your booking for %(service_name)s with %(owner_name)s is confirmed on %(date)s at %(time)s.") % {
            "service_name": service.name,
            "owner_name": owner.name,
            "date": booking.date.strftime('%Y-%m-%d'),
            "time": booking.time.strftime('%H:%M')
        }
        send_sms(booking.customer_phone, sms_body_customer)