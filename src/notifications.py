import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from twilio.rest import Client
import logging
from src.config import settings

logger = logging.getLogger(__name__)

# --- Email Notifications (SendGrid) ---
def send_email_notification(to_email: str, subject: str, body: str):
    """Sends an email notification using SendGrid."""
    if not settings.SENDGRID_API_KEY:
        logger.warning(f"SendGrid API key not set. Skipping email to {to_email}.")
        return False

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Email, To, Content

        sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
        from_email = Email("no-reply@bookslot.app") # Replace with your verified sender email
        to_email_obj = To(to_email)
        content = Content("text/html", body)
        mail = Mail(from_email, to_email_obj, subject, content)

        response = sg.client.mail.send.post(request_body=mail.get())

        if response.status_code == 202:
            logger.info(f"Email sent successfully to {to_email}")
            return True
        else:
            logger.error(f"Failed to send email to {to_email}. Status: {response.status_code}, Body: {response.body}")
            return False
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

# --- WhatsApp Notifications (Twilio) ---
def send_whatsapp_notification(to_phone_number: str, message: str):
    """Sends a WhatsApp notification using Twilio."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_WHATSAPP_NUMBER:
        logger.warning(f"Twilio credentials not fully set. Skipping WhatsApp to {to_phone_number}.")
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        # Twilio requires phone numbers in E.164 format (e.g., +1234567890)
        # We assume the `to_phone_number` is already in a compatible format or handle conversion.
        # For simplicity, we'll prefix with 'whatsapp:' for the To address.
        
        message_obj = client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}",
            body=message,
            to=f"whatsapp:{to_phone_number}"
        )
        logger.info(f"WhatsApp message sent successfully to {to_phone_number}. SID: {message_obj.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        return False

# --- Unified Notification Function ---
def send_booking_notification(owner_email: str, owner_phone: str, customer_email: str, customer_phone: str, booking_details: dict, is_owner_notification: bool):
    subject_template = "New Booking Confirmation for {service_name}" if is_owner_notification else "Your Booking Confirmation for {service_name}"
    body_template = """
    <html>
    <body>
        <p>Hello {recipient_name},</p>
        <p>This is a confirmation for your booking:</p>
        <ul>
            <li>Service: <b>{service_name}</b></li>
            <li>Date: <b>{booking_date}</b></li>
            <li>Time: <b>{booking_time}</b></li>
            <li>Customer Name: <b>{customer_name}</b></li>
            <li>Customer Email: <b>{customer_email}</b></li>
            <li>Customer Phone: <b>{customer_phone}</b></li>
        </ul>
        <p>Thank you!</p>
    </body>
    </html>
    """
    
    # Format details
    formatted_details = {
        "service_name": booking_details.get("service_name", "N/A"),
        "booking_date": booking_details.get("booking_date", "N/A"),
        "booking_time": booking_details.get("booking_time", "N/A"),
        "customer_name": booking_details.get("customer_name", "N/A"),
        "customer_email": booking_details.get("customer_email", "N/A"),
        "customer_phone": booking_details.get("customer_phone", "N/A"),
        "recipient_name": booking_details.get("owner_name", "Owner") if is_owner_notification else booking_details.get("customer_name", "Customer")
    }

    subject = subject_template.format(**formatted_details)
    body = body_template.format(**formatted_details)

    # Send email
    if is_owner_notification:
        send_email_notification(owner_email, subject, body)
    else:
        send_email_notification(customer_email, subject, body)

    # Send WhatsApp (only to owner for now, based on business idea)
    if is_owner_notification and owner_phone:
        whatsapp_message = f"New booking for {formatted_details['service_name']} on {formatted_details['booking_date']} at {formatted_details['booking_time']} by {formatted_details['customer_name']} ({formatted_details['customer_phone']})."
        send_whatsapp_notification(owner_phone, whatsapp_message)
