import httpx
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

async def send_booking_notification(owner_email: str, owner_phone: str, booking_details: dict, business_name: str):
    booking_time_str = booking_details['datetime'].strftime('%Y-%m-%d %H:%M') if isinstance(booking_details['datetime'], datetime) else booking_details['datetime']
    
    # Email content for owner
    owner_email_subject = f"New Booking for {business_name}"
    owner_email_body = (
        f"Dear {business_name} owner,\n\n"
        f"You have received a new booking!\n\n"
        f"Service: {booking_details['service']}\n"
        f"Date & Time: {booking_time_str}\n"
        f"Customer Name: {booking_details['customer_name']}\n"
        f"Customer Email: {booking_details['customer_email']}\n"
        f"Customer Phone: {booking_details['customer_phone']}\n\n"
        f"Thank you for using BookSlot!"
    )

    # 1. Send Email via SendGrid to owner
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {os.getenv('SENDGRID_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "personalizations": [{"to": [{"email": owner_email}]}],
                "from": {"email": "bookings@bookslot.app", "name": "BookSlot"},
                "subject": owner_email_subject,
                "content": [{"type": "text/plain", "value": owner_email_body}]
            }
        )
    
    # 2. Trigger WhatsApp via Twilio to owner
    twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
    twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
    twilio_number = os.getenv('TWILIO_WHATSAPP_NUMBER')
    
    if twilio_sid and twilio_token and owner_phone:
        whatsapp_body = (
            f"New Booking for {business_name}!\n"
            f"Service: {booking_details['service']}\n"
            f"Time: {booking_time_str}\n"
            f"Customer: {booking_details['customer_name']}\n"
            f"Phone: {booking_details['customer_phone']}"
        )
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json",
                    auth=(twilio_sid, twilio_token),
                    data={
                        "From": f"whatsapp:{twilio_number}",
                        "To": f"whatsapp:{owner_phone}",
                        "Body": whatsapp_body
                    }
                )
            except httpx.HTTPStatusError as e:
                print(f"Twilio WhatsApp error: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                print(f"An unexpected error occurred with Twilio: {e}")

async def send_customer_confirmation_email(customer_email: str, booking_details: dict, business_name: str):
    booking_time_str = booking_details['datetime'].strftime('%Y-%m-%d %H:%M') if isinstance(booking_details['datetime'], datetime) else booking_details['datetime']

    customer_email_subject = f"Your booking confirmation with {business_name}"
    customer_email_body = (
        f"Dear {booking_details['customer_name']}, \n\n"
        f"Thank you for booking with {business_name}!\n\n"
        f"Your booking details are:\n"
        f"Service: {booking_details['service']}\n"
        f"Date & Time: {booking_time_str}\n"
        f"We look forward to seeing you.\n\n"
        f"Best regards,\n"
        f"The {business_name} Team"
    )

    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {os.getenv('SENDGRID_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "personalizations": [{"to": [{"email": customer_email}]}],
                "from": {"email": "noreply@bookslot.app", "name": "BookSlot"},
                "subject": customer_email_subject,
                "content": [{"type": "text/plain", "value": customer_email_body}]
            }
        )
