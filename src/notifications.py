from typing import Optional
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
from . import models
from .i18n import gettext_lazy as _ # Assuming i18n is also used for notification texts

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        print("SendGrid API key not configured. Skipping email.")
        return

    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender
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

def send_whatsapp_message(to_phone: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        print("Twilio credentials not configured. Skipping WhatsApp message.")
        return

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=message_body,
            to=f"whatsapp:{to_phone}"
        )
        print(f"WhatsApp message sent to {to_phone}. SID: {message.sid}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone}: {e}")

def send_booking_confirmation_email(booking: models.Booking, owner: models.Owner, locale: str = 'en'):
    # This function needs to be locale-aware for subject and body
    # For simplicity, I'll use placeholders for i18n functions
    # In a real app, you'd pass the locale or use a context-aware i18n system.
    # Here, I'm simulating it by directly including service_name.

    # Example: Subject and body could be rendered from templates or constructed dynamically
    # For a full i18n solution, this would involve a proper translation context.
    # Here, I'm simulating it by directly including service_name.

    subject = _("Booking Confirmation for your appointment at {business_name}", locale=locale).format(business_name=owner.business_name)
    customer_html_content = f"""
    <html>
        <body>
            <p>{_("Dear {customer_name},", locale=locale).format(customer_name=booking.customer_name)}</p>
            <p>{_("Your booking for {service_name} at {business_name} has been confirmed.", locale=locale).format(service_name=booking.service_name, business_name=owner.business_name)}</p>
            <p>{_("Details:", locale=locale)}</p>
            <ul>
                <li>{_("Service:", locale=locale)} {booking.service_name}</li>
                <li>{_("Date:", locale=locale)} {booking.booking_date.strftime('%Y-%m-%d')}</li>
                <li>{_("Time:", locale=locale)} {booking.booking_time.strftime('%H:%M')}</li>
                <li>{_("Business:", locale=locale)} {owner.business_name}</li>
            </ul>
            <p>{_("Thank you!", locale=locale)}</p>
        </body>
    </html>
    """
    send_email(booking.customer_email, subject, customer_html_content)

    owner_subject = _("New Booking Received for {service_name}!", locale=locale).format(service_name=booking.service_name)
    owner_html_content = f"""
    <html>
        <body>
            <p>{_("Dear {owner_name},", locale=locale).format(owner_name=owner.name)}</p>
            <p>{_("You have received a new booking:", locale=locale)}</p>
            <ul>
                <li>{_("Service:", locale=locale)} {booking.service_name}</li>
                <li>{_("Customer Name:", locale=locale)} {booking.customer_name}</li>
                <li>{_("Customer Email:", locale=locale)} {booking.customer_email}</li>
                <li>{_("Customer Phone:", locale=locale)} {booking.customer_phone if booking.customer_phone else _('N/A', locale=locale)}</li>
                <li>{_("Date:", locale=locale)} {booking.booking_date.strftime('%Y-%m-%d')}</li>
                <li>{_("Time:", locale=locale)} {booking.booking_time.strftime('%H:%M')}</li>
            </ul>
            <p>{_("Manage your bookings:", locale=locale)} <a href=\"{settings.SERVER_NAME}/dashboard\">{settings.SERVER_NAME}/dashboard</a></p>
        </body>
    </html>
    """
    send_email(owner.email, owner_subject, owner_html_content)

def send_owner_whatsapp_notification(booking: models.Booking, owner: models.Owner, locale: str = 'en'):
    if not owner.phone:
        return
    message_body = _("New Booking for {service_name}!\nCustomer: {customer_name}\nDate: {booking_date}\nTime: {booking_time}\nEmail: {customer_email}\nPhone: {customer_phone}", locale=locale).format(
        service_name=booking.service_name,
        customer_name=booking.customer_name,
        booking_date=booking.booking_date.strftime('%Y-%m-%d'),
        booking_time=booking.booking_time.strftime('%H:%M'),
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone if booking.customer_phone else _('N/A', locale=locale)
    )
    send_whatsapp_message(owner.phone, message_body)

def send_customer_whatsapp_notification(booking: models.Booking, owner: models.Owner, locale: str = 'en'):
    if not booking.customer_phone:
        return
    message_body = _("Your booking for {service_name} at {business_name} is confirmed!\nDate: {booking_date}\nTime: {booking_time}", locale=locale).format(
        service_name=booking.service_name,
        business_name=owner.business_name,
        booking_date=booking.booking_date.strftime('%Y-%m-%d'),
        booking_time=booking.booking_time.strftime('%H:%M')
    )
    send_whatsapp_message(booking.customer_phone, message_body)
