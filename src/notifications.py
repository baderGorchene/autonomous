from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings
from src import models
from gettext import gettext as _

def send_email(to_email: str, subject: str, html_content: str):
    if not settings.SENDGRID_API_KEY:
        print(f"Skipping email to {to_email} (no SendGrid API Key): {subject}")
        return

    message = Mail(
        from_email='no-reply@bookslot.app',
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
        print(f"Skipping WhatsApp to {to_phone} (Twilio not configured): {message_body}")
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
        print(f"Error sending WhatsApp to {to_phone}: {e}")

def send_booking_confirmation_email(owner: models.Owner, service: models.Service, booking: models.Booking):
    subject = _("Your Booking Confirmation")
    html_content = f"""
    <html>
        <body>
            <p>{_('Hello')} {booking.customer_name},</p>
            <p>{_('Your booking for')} {service.name} {_('with')} {owner.name} {_('is confirmed.')}</p>
            <p>{_('Service')}: {service.name}</p>
            <p>{_('Time')}: {booking.start_time.strftime('%Y-%m-%d %H:%M')}</p>
            <p>{_('Price')}: {service.price}</p>
            <p>{_('We look forward to seeing you!')}</p>
        </body>
    </html>
    """
    send_email(booking.customer_email, subject, html_content)

def send_booking_notification_to_owner(owner: models.Owner, service: models.Service, booking: models.Booking):
    subject = _("New Booking Received!")
    html_content = f"""
    <html>
        <body>
            <p>{_('Hello')} {owner.name},</p>
            <p>{_('You have received a new booking:')}</p>
            <ul>
                <li>{_('Service')}: {service.name}</li>
                <li>{_('Customer')}: {booking.customer_name} ({booking.customer_email})</li>
                <li>{_('Phone')}: {booking.customer_phone or _('N/A')}</li>
                <li>{_('Time')}: {booking.start_time.strftime('%Y-%m-%d %H:%M')}</li>
            </ul>
            <p>{_('Please check your dashboard for more details.')}</p>
        </body>
    </html>
    """
    send_email(owner.email, subject, html_content)
    if owner.phone:
        whatsapp_message = f"{_('New booking for')} {service.name} {_('with')} {booking.customer_name} {_('at')} {booking.start_time.strftime('%Y-%m-%d %H:%M')}. {_('Check your dashboard.')}"
        send_whatsapp_message(owner.phone, whatsapp_message)

def send_subscription_confirmation_email(owner: models.Owner, subscription: models.Subscription):
    subject = _("Your BookSlot Subscription is Active!")
    html_content = f"""
    <html>
        <body>
            <p>{_('Hello')} {owner.name},</p>
            <p>{_('Your BookSlot premium subscription is now active!')}</p>
            <p>{_('Subscription ID')}: {subscription.stripe_subscription_id}</p>
            <p>{_('Status')}: {subscription.status}</p>
            <p>{_('Next billing date')}: {subscription.current_period_end.strftime('%Y-%m-%d')}</p>
            <p>{_('Thank you for choosing BookSlot!')}</p>
        </body>
    </html>
    """
    send_email(owner.email, subject, html_content)
