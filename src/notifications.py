from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client
from src.config import settings
import logging

logger = logging.getLogger(__name__)

def send_email_notification(to_email: str, subject: str, html_content: str):
    try:
        message = Mail(
            from_email='noreply@bookslot.app',
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        sendgrid_client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        logger.info(f"Email sent to {to_email}, status code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_notification(to_phone_number: str, message_body: str):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            to=f"whatsapp:{to_phone_number}",
            body=message_body
        )
        logger.info(f"WhatsApp message sent to {to_phone_number}, SID: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        return False

def format_booking_details(booking_data: dict, owner_name: str, business_name: str, language: str = 'en'):
    if language == 'ar':
        return f"حجز جديد لـ {business_name}:\nالخدمة: {booking_data['service_name']}\nالتاريخ والوقت: {booking_data['booking_time'].strftime('%Y-%m-%d %H:%M')}\nالعميل: {booking_data['customer_name']}\nالبريد الإلكتروني: {booking_data['customer_email']}\nالهاتف: {booking_data.get('customer_phone', 'غير متوفر')}"
    elif language == 'fr':
        return f"Nouvelle réservation pour {business_name}:\nService: {booking_data['service_name']}\nDate et heure: {booking_data['booking_time'].strftime('%Y-%m-%d %H:%M')}\nClient: {booking_data['customer_name']}\nEmail: {booking_data['customer_email']}\nTéléphone: {booking_data.get('customer_phone', 'Non disponible')}"
    else:
        return f"New booking for {business_name}:\nService: {booking_data['service_name']}\nDate & Time: {booking_data['booking_time'].strftime('%Y-%m-%d %H:%M')}\nCustomer: {booking_data['customer_name']}\nEmail: {booking_data['customer_email']}\nPhone: {booking_data.get('customer_phone', 'N/A')}"

def send_booking_confirmation(booking: dict, owner_email: str, owner_phone: Optional[str], owner_name: str, business_name: str, customer_email: str, customer_phone: Optional[str], language: str = 'en'):
    owner_subject = "New Booking Notification" if language == 'en' else "إشعار حجز جديد" if language == 'ar' else "Nouvelle notification de réservation"
    owner_html_content = f"<p>{format_booking_details(booking, owner_name, business_name, language).replace('\n', '<br>')}</p>"
    send_email_notification(owner_email, owner_subject, owner_html_content)
    if owner_phone:
        send_whatsapp_notification(owner_phone, format_booking_details(booking, owner_name, business_name, language))

    customer_subject = "Your Booking Confirmation" if language == 'en' else "تأكيد حجزك" if language == 'ar' else "Confirmation de votre réservation"
    customer_html_content = f"<p>Dear {booking['customer_name']},</p><p>Your booking for {booking['service_name']} at {business_name} on {booking['booking_time'].strftime('%Y-%m-%d %H:%M')} has been confirmed.</p><p>Thank you!</p>"
    if language == 'ar':
        customer_html_content = f"<p>عزيزي {booking['customer_name']},</p><p>تم تأكيد حجزك لـ {booking['service_name']} في {business_name} بتاريخ {booking['booking_time'].strftime('%Y-%m-%d %H:%M')}.</p><p>شكرا لك!</p>"
    elif language == 'fr':
        customer_html_content = f"<p>Cher {booking['customer_name']},</p><p>Votre réservation pour {booking['service_name']} chez {business_name} le {booking['booking_time'].strftime('%Y-%m-%d %H:%M')} a été confirmée.</p><p>Merci!</p>"

    send_email_notification(customer_email, customer_subject, customer_html_content)
    if customer_phone:
        customer_whatsapp_message = f"Hi {booking['customer_name']}, your booking for {booking['service_name']} at {business_name} on {booking['booking_time'].strftime('%Y-%m-%d %H:%M')} is confirmed."
        if language == 'ar':
            customer_whatsapp_message = f"مرحبا {booking['customer_name']}، تم تأكيد حجزك لـ {booking['service_name']} في {business_name} بتاريخ {booking['booking_time'].strftime('%Y-%m-%d %H:%M')}."
        elif language == 'fr':
            customer_whatsapp_message = f"Bonjour {booking['customer_name']}, votre réservation pour {booking['service_name']} chez {business_name} le {booking['booking_time'].strftime('%Y-%m-%d %H:%M')} est confirmée."

        send_whatsapp_notification(customer_phone, customer_whatsapp_message)
