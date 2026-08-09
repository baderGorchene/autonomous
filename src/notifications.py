import sendgrid
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
from . import models
from datetime import date, time

sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY or settings.SENDGRID_API_KEY == "SG....":
        print(f"Email to {to_email}: Subject: {subject}, Content: {html_content}")
        return
    message = Mail(
        from_email='noreply@bookslot.app',
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        response = sg.send(message)
        print(f"Email sent. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email: {e}")

def send_sms(to_phone_number: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or settings.TWILIO_ACCOUNT_SID == "AC....":
        print(f"SMS to {to_phone_number}: Content: {message_body}")
        return
    try:
        message = twilio_client.messages.create(
            to=to_phone_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            body=message_body
        )
        print(f"SMS sent. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending SMS: {e}")

def send_booking_confirmation(owner: models.Owner, customer: models.Customer, service: models.Service, booking: models.Booking, _):
    customer_subject = _("Your booking for {service_name} on {date} at {time} is confirmed!").format(
        service_name=service.name, date=booking.date.strftime('%Y-%m-%d'), time=booking.time.strftime('%H:%M')
    )
    customer_body = _("Hi {customer_name},<br><br>Your booking with {owner_username} for {service_name} on {date} at {time} is confirmed.<br>Service: {service_name}<br>Date: {date}<br>Time: {time}<br>Owner Contact: {owner_email} / {owner_phone}<br><br>Thank you!").format(
        customer_name=customer.name, owner_username=owner.username, service_name=service.name,
        date=booking.date.strftime('%Y-%m-%d'), time=booking.time.strftime('%H:%M'),
        owner_email=owner.email, owner_phone=owner.phone_number
    )
    send_email(customer.email, customer_subject, customer_body)

    owner_subject = _("New booking for {service_name} on {date} at {time} from {customer_name}").format(
        service_name=service.name, date=booking.date.strftime('%Y-%m-%d'), time=booking.time.strftime('%H:%M'), customer_name=customer.name
    )
    owner_body = _("Hello {owner_username},<br><br>You have a new booking:<br>Service: {service_name}<br>Date: {date}<br>Time: {time}<br>Customer: {customer_name}<br>Customer Email: {customer_email}<br>Customer Phone: {customer_phone}<br><br>View on your dashboard: {dashboard_link}").format(
        owner_username=owner.username, service_name=service.name,
        date=booking.date.strftime('%Y-%m-%d'), time=booking.time.strftime('%H:%M'),
        customer_name=customer.name, customer_email=customer.email, customer_phone=customer.phone_number,
        dashboard_link="https://bookslot.app/dashboard" # TODO: Make dynamic
    )
    send_email(owner.email, owner_subject, owner_body)

    owner_sms_body = _("New booking: {service_name} on {date} at {time} from {customer_name}. Check dashboard for details.").format(
        service_name=service.name, date=booking.date.strftime('%Y-%m-%d'), time=booking.time.strftime('%H:%M'), customer_name=customer.name
    )
    if owner.phone_number:
        send_sms(owner.phone_number, owner_sms_body)
