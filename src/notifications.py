import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
import logging
import gettext # Added import

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str):
    message = Mail(
        from_email='no-reply@bookslot.app', # Replace with your verified sender
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_message(to_number: str, message_body: str):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            to=f'whatsapp:{to_number}',
            body=message_body
        )
        logger.info(f"WhatsApp message sent to {to_number}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_number}: {e}")
        return False

def format_booking_details(booking_data: dict, owner_name: str, business_name: str, locale: str = 'en'):
    # This function would be more sophisticated with actual i18n
    # For now, it's a placeholder.
    # In a real app, you'd use gettext for these strings.
    if locale == 'ar':
        # Example Arabic translation - needs actual translation strings
        return (
            f"تم تأكيد حجزك مع {owner_name} - {business_name}\n"
            f"الخدمة: {booking_data['service_name']}\n"
            f"الوقت: {booking_data['booking_time'].strftime('%Y-%m-%d %H:%M')}\n"
            f"المدة: {booking_data['duration_minutes']} دقيقة\n"
            f"العميل: {booking_data['customer_name']}\n"
            f"الهاتف: {booking_data['customer_phone'] or 'غير متوفر'}"
        )
    elif locale == 'fr':
        # Example French translation
        return (
            f"Votre réservation est confirmée avec {owner_name} - {business_name}\n"
            f"Service: {booking_data['service_name']}\n"
            f"Heure: {booking_data['booking_time'].strftime('%Y-%m-%d %H:%M')}\n"
            f"Durée: {booking_data['duration_minutes']} minutes\n"
            f"Client: {booking_data['customer_name']}\n"
            f"Téléphone: {booking_data['customer_phone'] or 'Non disponible'}"
        )
    else: # English fallback
        return (
            f"Your booking with {owner_name} - {business_name} is confirmed!\n"
            f"Service: {booking_data['service_name']}\n"
            f"Time: {booking_data['booking_time'].strftime('%Y-%m-%d %H:%M')}\n"
            f"Duration: {booking_data['duration_minutes']} minutes\n"
            f"Customer: {booking_data['customer_name']}\n"
            f"Phone: {booking_data['customer_phone'] or 'N/A'}"
        )

# Placeholder for email templates - in a real app these would be Jinja2 templates
def get_owner_booking_email_html(booking_details: dict, owner_name: str, business_name: str, customer_email: str, locale: str = 'en'):
    # This should ideally load a Jinja2 template
    _ = lambda x: x # Placeholder for gettext
    try:
        if locale == 'ar':
            _ = gettext.translation('messages', settings.LOCALES_DIR, languages=['ar'], fallback=True).gettext
        elif locale == 'fr':
            _ = gettext.translation('messages', settings.LOCALES_DIR, languages=['fr'], fallback=True).gettext
    except Exception:
        pass # Fallback to default if translation fails

    return f"""
    <html>
        <body>
            <p>{_('New Booking for your Business!')}</p>
            <p><strong>{_('Business Name')}:</strong> {business_name}</p>
            <p><strong>{_('Service')}:</strong> {booking_details['service_name']}</p>
            <p><strong>{_('Time')}:</strong> {booking_details['booking_time'].strftime('%Y-%m-%d %H:%M')}</p>
            <p><strong>{_('Duration')}:</strong> {booking_details['duration_minutes']} {_('minutes')}</p>
            <p><strong>{_('Customer Name')}:</strong> {booking_details['customer_name']}</p>
            <p><strong>{_('Customer Email')}:</strong> {customer_email}</p>
            <p><strong>{_('Customer Phone')}:</strong> {booking_details.get('customer_phone', _('N/A'))}</p>
            <p>{_('Manage your bookings in your dashboard.')}</p>
        </body>
    </html>
    """

def get_customer_confirmation_email_html(booking_details: dict, owner_name: str, business_name: str, locale: str = 'en'):
    # This should ideally load a Jinja2 template
    _ = lambda x: x # Placeholder for gettext
    try:
        if locale == 'ar':
            _ = gettext.translation('messages', settings.LOCALES_DIR, languages=['ar'], fallback=True).gettext
        elif locale == 'fr':
            _ = gettext.translation('messages', settings.LOCALES_DIR, languages=['fr'], fallback=True).gettext
    except Exception:
        pass # Fallback to default if translation fails

    return f"""
    <html>
        <body>
            <p>{_('Your Booking is Confirmed!')}</p>
            <p>{_('Hello')} {booking_details['customer_name']},</p>
            <p>{_('Your booking with')} <strong>{owner_name} - {business_name}</strong> {_('is confirmed.')}</p>
            <p><strong>{_('Service')}:</strong> {booking_details['service_name']}</p>
            <p><strong>{_('Time')}:</strong> {booking_details['booking_time'].strftime('%Y-%m-%d %H:%M')}</p>
            <p><strong>{_('Duration')}:</strong> {booking_details['duration_minutes']} {_('minutes')}</p>
            <p>{_('We look forward to seeing you!')}</p>
        </body>
    </html>
    """
