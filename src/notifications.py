import os
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To
from twilio.rest import Client
from .config import settings

def send_email_notification(to_email: str, subject: str, html_content: str):
    try:
        sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
        from_email = Email("no-reply@bookslot.app") # Replace with your verified sender
        to_email_obj = To(to_email)
        message = Mail(from_email, to_email_obj, subject, html_content=html_content)
        response = sg.send(message)
        print(f"Email sent to {to_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_notification(to_phone_number: str, message_body: str):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            body=message_body,
            to=f"whatsapp:{to_phone_number}"
        )
        print(f"WhatsApp message sent to {to_phone_number}. SID: {message.sid}")
        return True
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone_number}: {e}")
        return False

def send_booking_confirmation(booking_details: dict, owner_email: str, owner_phone: str, customer_email: str, customer_phone: str, locale: str = 'en'):
    # This is a placeholder. In a real app, you'd load templates based on locale.
    # For simplicity, we'll use basic strings here, but the Jinja2 templates should be used.
    
    # Email content for customer
    customer_subject = f"Your booking with {booking_details['business_name']} is confirmed!"
    customer_email_html = f"""
    <p>Hi {booking_details['customer_name']},</p>
    <p>Your booking for {booking_details['service_name']} on {booking_details['booking_date']} at {booking_details['booking_time']} with {booking_details['business_name']} is confirmed.</p>
    <p>Thank you!</p>
    """
    send_email_notification(customer_email, customer_subject, customer_email_html)

    # Email content for owner
    owner_subject = f"New booking received for {booking_details['service_name']}!"
    owner_email_html = f"""
    <p>Hello {booking_details['owner_name']},</p>
    <p>You have a new booking:</p>
    <ul>
        <li>Service: {booking_details['service_name']}</li>
        <li>Date: {booking_details['booking_date']}</li>
        <li>Time: {booking_details['booking_time']}</li>
        <li>Customer: {booking_details['customer_name']}</li>
        <li>Customer Email: {booking_details['customer_email']}</li>
        <li>Customer Phone: {booking_details['customer_phone']}</li>
    </ul>
    <p>Please check your dashboard for more details.</p>
    """
    send_email_notification(owner_email, owner_subject, owner_email_html)

    # WhatsApp content for owner
    whatsapp_message = f"New booking!\nService: {booking_details['service_name']}\nDate: {booking_details['booking_date']} at {booking_details['booking_time']}\nCustomer: {booking_details['customer_name']} ({booking_details['customer_phone']})"
    send_whatsapp_notification(owner_phone, whatsapp_message)
