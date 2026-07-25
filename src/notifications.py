import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from .config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str):
    message = Mail(
        from_email='no-reply@bookslot.app', # This needs to be a verified sender in SendGrid
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return response.status_code == 202
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_notification(to_phone: str, message_body: str):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning("Twilio credentials not fully configured. Skipping WhatsApp notification.")
        return False
        
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f'whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}',
            body=message_body,
            to=f'whatsapp:{to_phone}'
        )
        logger.info(f"WhatsApp message sent to {to_phone}. SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone}: {e}")
        return False

def format_booking_details(booking_data: dict, owner_name: str, business_name: str, locale: str = 'en'):
    # This is a simplified version. In a real app, you'd use gettext for proper i18n
    # and potentially a template engine for richer emails.
    if locale == 'ar':
        # Arabic specific formatting
        return f"""
        <html>
        <head></head>
        <body>
            <p>مرحباً {booking_data['customer_name']},</p>
            <p>تم تأكيد حجزك لدى {business_name}!</p>
            <p>التفاصيل:</p>
            <ul>
                <li>الخدمة: {booking_data['service_name']}</li>
                <li>التاريخ: {booking_data['booking_date'].strftime('%Y-%m-%d')}</li>
                <li>الوقت: {booking_data['booking_time']}</li>
            </ul>
            <p>نحن نتطلع لرؤيتك!</p>
            <p>مع تحيات،<br>{owner_name}</p>
        </body>
        </html>
        """
    elif locale == 'fr':
        # French specific formatting
        return f"""
        <html>
        <head></head>
        <body>
            <p>Bonjour {booking_data['customer_name']},</p>
            <p>Votre réservation avec {business_name} a été confirmée !</p>
            <p>Détails:</p>
            <ul>
                <li>Service: {booking_data['service_name']}</li>
                <li>Date: {booking_data['booking_date'].strftime('%Y-%m-%d')}</li>
                <li>Heure: {booking_data['booking_time']}</li>
            </ul>
            <p>Nous avons hâte de vous voir !</p>
            <p>Cordialement,<br>{owner_name}</p>
        </body>
        </html>
        """
    else:
        # English default
        return f"""
        <html>
        <head></head>
        <body>
            <p>Hi {booking_data['customer_name']},</p>
            <p>Your booking with {business_name} has been confirmed!</p>
            <p>Details:</p>
            <ul>
                <li>Service: {booking_data['service_name']}</li>
                <li>Date: {booking_data['booking_date'].strftime('%Y-%m-%d')}</li>
                <li>Time: {booking_data['booking_time']}</li>
            </ul>
            <p>We look forward to seeing you!</p>
            <p>Best regards,<br>{owner_name}</p>
        </body>
        </html>
        """

def format_owner_notification(booking_data: dict, business_name: str, owner_name: str, locale: str = 'en'):
    if locale == 'ar':
        return f"""
        <html>
        <head></head>
        <body>
            <p>مرحباً {owner_name},</p>
            <p>لديك حجز جديد لـ {business_name}!</p>
            <p>التفاصيل:</p>
            <ul>
                <li>العميل: {booking_data['customer_name']}</li>
                <li>البريد الإلكتروني للعميل: {booking_data['customer_email']}</li>
                <li>رقم هاتف العميل: {booking_data['customer_phone'] or 'غير متوفر'}</li>
                <li>الخدمة: {booking_data['service_name']}</li>
                <li>التاريخ: {booking_data['booking_date'].strftime('%Y-%m-%d')}</li>
                <li>الوقت: {booking_data['booking_time']}</li>
            </ul>
            <p>مع تحيات،<br>فريق BookSlot</p>
        </body>
        </html>
        """
    elif locale == 'fr':
        return f"""
        <html>
        <head></head>
        <body>
            <p>Bonjour {owner_name},</p>
            <p>Vous avez une nouvelle réservation pour {business_name} !</p>
            <p>Détails:</p>
            <ul>
                <li>Client: {booking_data['customer_name']}</li>
                <li>Email du client: {booking_data['customer_email']}</li>
                <li>Téléphone du client: {booking_data['customer_phone'] or 'Non disponible'}</li>
                <li>Service: {booking_data['service_name']}</li>
                <li>Date: {booking_data['booking_date'].strftime('%Y-%m-%d')}</li>
                <li>Heure: {booking_data['booking_time']}</li>
            </ul>
            <p>Cordialement,<br>L'équipe BookSlot</p>
        </body>
        </html>
        """
    else:
        return f"""
        <html>
        <head></head>
        <body>
            <p>Hi {owner_name},</p>
            <p>You have a new booking for {business_name}!</p>
            <p>Details:</p>
            <ul>
                <li>Customer: {booking_data['customer_name']}</li>
                <li>Customer Email: {booking_data['customer_email']}</li>
                <li>Customer Phone: {booking_data['customer_phone'] or 'N/A'}</li>
                <li>Service: {booking_data['service_name']}</li>
                <li>Date: {booking_data['booking_date'].strftime('%Y-%m-%d')}</li>
                <li>Time: {booking_data['booking_time']}</li>
            </ul>
            <p>Best regards,<br>The BookSlot Team</p>
        </body>
        </html>
        """

def format_owner_whatsapp_notification(booking_data: dict, business_name: str, owner_name: str, locale: str = 'en'):
    if locale == 'ar':
        return (
            f"مرحباً {owner_name},\n"
            f"لديك حجز جديد لـ {business_name}!\n"
            f"العميل: {booking_data['customer_name']}\n"
            f"الخدمة: {booking_data['service_name']}\n"
            f"التاريخ: {booking_data['booking_date'].strftime('%Y-%m-%d')}\n"
            f"الوقت: {booking_data['booking_time']}\n"
            f"للتواصل: {booking_data['customer_email']} / {booking_data['customer_phone'] or 'غير متوفر'}"
        )
    elif locale == 'fr':
        return (
            f"Bonjour {owner_name},\n"
            f"Vous avez une nouvelle réservation pour {business_name} !\n"
            f"Client: {booking_data['customer_name']}\n"
            f"Service: {booking_data['service_name']}\n"
            f"Date: {booking_data['booking_date'].strftime('%Y-%m-%d')}\n"
            f"Heure: {booking_data['booking_time']}\n"
            f"Contact: {booking_data['customer_email']} / {booking_data['customer_phone'] or 'Non disponible'}"
        )
    else:
        return (
            f"Hi {owner_name},\n"
            f"You have a new booking for {business_name}!\n"
            f"Customer: {booking_data['customer_name']}\n"
            f"Service: {booking_data['service_name']}\n"
            f"Date: {booking_data['booking_date'].strftime('%Y-%m-%d')}\n"
            f"Time: {booking_data['booking_time']}\n"
            f"Contact: {booking_data['customer_email']} / {booking_data['customer_phone'] or 'N/A'}"
        )
