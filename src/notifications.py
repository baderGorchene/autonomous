import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from typing import Optional

from . import schemas, models
from .config import settings
from .i18n import get_translator

def _send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY or settings.SENDGRID_API_KEY == "SG....":
        print(f"Skipping email to {to_email}: SENDGRID_API_KEY not configured.")
        return

    message = Mail(
        from_email='noreply@bookslot.app', # TODO: configure a proper sender email in settings
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

def _send_sms(to_phone_number: str, body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_PHONE_NUMBER:
        print(f"Skipping SMS to {to_phone_number}: Twilio credentials not configured.")
        return
    
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=settings.TWILIO_PHONE_NUMBER,
            to=to_phone_number,
            body=body
        )
        print(f"SMS sent to {to_phone_number}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending SMS to {to_phone_number}: {e}")

def send_booking_confirmation_email(
    booking: models.Booking,
    service: models.Service,
    owner: models.Owner,
    customer_name: str,
    customer_email: str,
    locale: str = "en"
):
    _ = get_translator(locale)

    is_recurring = booking.recurrence_id is not None
    recurring_note = _("<p>This is part of a recurring booking series.</p>") if is_recurring else ""

    subject = _("Your Booking Confirmation")
    html_content = f"""
        <html>
            <body>
                <p>{_("Dear")} {customer_name},</p>
                <p>{_("This is to confirm your booking for the service")}: <strong>{service.name}</strong> {_("with")} <strong>{owner.name}</strong>.</p>
                <p>{_("Date")}: {booking.date.strftime('%Y-%m-%d')}</p>
                <p>{_("Time")}: {booking.time.strftime('%H:%M')}</p>
                <p>{_("Location")}: {owner.address or _("Not specified")}</p>
                {recurring_note}
                <p>{_("We look forward to seeing you!")}</p>
                <p>{_("Thank you for choosing BookSlot!")}</p>
            </body>
        </html>
    """
    _send_email(customer_email, subject, html_content)

def send_owner_notification(
    booking: models.Booking,
    service: models.Service,
    owner: models.Owner,
    customer_name: str,
    customer_email: str,
    customer_phone: Optional[str],
    locale: str = "en"
):
    _ = get_translator(locale)

    is_recurring = booking.recurrence_id is not None
    recurring_email_note = _("<p>This booking is part of a recurring series.</p>") if is_recurring else ""
    recurring_sms_note = _(" (Recurring booking)") if is_recurring else ""


    if owner.email:
        subject = _("New Booking Received!")
        html_content = f"""
            <html>
                <body>
                    <p>{_("Dear")} {owner.name},</p>
                    <p>{_("You have received a new booking for your service")}: <strong>{service.name}</strong>.</p>
                    <p>{_("Customer")}: {customer_name}</p>
                    <p>{_("Customer Email")}: {customer_email}</p>
                    <p>{_("Date")}: {booking.date.strftime('%Y-%m-%d')}</p>
                    <p>{_("Time")}: {booking.time.strftime('%H:%M')}</p>
                    {recurring_email_note}
                    <p>{_("BookSlot Team")}</p>
                </body>
            </html>
        """
        _send_email(owner.email, subject, html_content)

    if owner.phone_number: # Twilio credentials check is inside _send_sms
        sms_body = _("New booking for {service_name} from {customer_name} on {date} at {time}{recurring_note}.").format(
            service_name=service.name,
            customer_name=customer_name,
            date=booking.date.strftime('%Y-%m-%d'),
            time=booking.time.strftime('%H:%M'),
            recurring_note=recurring_sms_note
        )
        _send_sms(owner.phone_number, sms_body)
