from datetime import datetime
from typing import Optional
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
from . import models, i18n

def send_booking_confirmation(booking: models.Booking, owner: models.Owner, service: models.Service):
    _ = i18n.gettext # Initialize gettext for this context

    customer_name = booking.customer.name if booking.customer else booking.customer_name
    customer_email = booking.customer.email if booking.customer else booking.customer_email

    if not customer_email:
        print(f"Skipping customer email confirmation for booking {booking.id}: No customer email provided.")
        return

    subject = _("Your Booking Confirmation for {service_name}").format(service_name=service.name)
    body = _("""
        Dear {customer_name},

        Your booking for {service_name} on {date} at {time} has been confirmed.

        Service Provider: {owner_name}
        Service: {service_name}
        Date: {date}
        Time: {time}
        Duration: {duration_minutes} minutes

        We look forward to seeing you!

        Best regards,
        The {owner_name} Team
    """).format(
        customer_name=customer_name,
        service_name=service.name,
        date=booking.date.strftime("%Y-%m-%d"),
        time=booking.time.strftime("%H:%M"),
        duration_minutes=service.duration_minutes,
        owner_name=owner.username
    )

    try:
        message = Mail(
            from_email='no-reply@bookslot.app',
            to_emails=customer_email,
            subject=subject,
            html_content=f'<p>{body.replace("\n", "<br>")}</p>'
        )
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Customer email confirmation sent. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending customer email confirmation for booking {booking.id}: {e}")


def send_booking_notification_to_owner(booking: models.Booking, owner: models.Owner, service: models.Service):
    _ = i18n.gettext # Initialize gettext for this context

    owner_email = owner.email
    owner_phone = owner.phone_number

    customer_name = booking.customer.name if booking.customer else booking.customer_name
    customer_email = booking.customer.email if booking.customer else booking.customer_email
    customer_phone = booking.customer.phone_number if booking.customer else booking.customer_phone

    # Email notification to owner
    if owner_email:
        email_subject = _("New Booking for {service_name}").format(service_name=service.name)
        email_body = _("""
            Dear {owner_name},

            You have a new booking!

            Customer Name: {customer_name}
            Customer Email: {customer_email}
            Customer Phone: {customer_phone}
            Service: {service_name}
            Date: {date}
            Time: {time}
            Duration: {duration_minutes} minutes
            
            Booking ID: {booking_id}
            {is_recurring_text}
        """).format(
            owner_name=owner.username,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone if customer_phone else _("Not provided"),
            service_name=service.name,
            date=booking.date.strftime("%Y-%m-%d"),
            time=booking.time.strftime("%H:%M"),
            duration_minutes=service.duration_minutes,
            booking_id=booking.id,
            is_recurring_text=_("This is a recurring booking.") if booking.is_recurring else ""
        )
        try:
            message = Mail(
                from_email='no-reply@bookslot.app',
                to_emails=owner_email,
                subject=email_subject,
                html_content=f'<p>{email_body.replace("\n", "<br>")}</p>'
            )
            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
            response = sg.send(message)
            print(f"Owner email notification sent. Status Code: {response.status_code}")
        except Exception as e:
            print(f"Error sending owner email notification for booking {booking.id}: {e}")

    # SMS notification to owner
    if owner_phone and settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_PHONE_NUMBER:
        sms_body = _("""
            New Booking!
            Customer: {customer_name} ({customer_phone})
            Service: {service_name}
            Date: {date} @ {time}
        """).format(
            customer_name=customer_name,
            customer_phone=customer_phone if customer_phone else _("N/A"),
            service_name=service.name,
            date=booking.date.strftime("%Y-%m-%d"),
            time=booking.time.strftime("%H:%M")
        )
        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                to=owner_phone,
                from_=settings.TWILIO_PHONE_NUMBER,
                body=sms_body
            )
            print(f"Owner SMS notification sent. SID: {message.sid}")
        except Exception as e:
            print(f"Error sending owner SMS notification for booking {booking.id}: {e}")
