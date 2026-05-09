import httpx
import os
from dotenv import load_dotenv

load_dotenv()

async def send_booking_notification(owner_email: str, owner_phone: str, booking_details: dict):
    # 1. Send Email via SendGrid
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {os.getenv('SENDGRID_API_KEY')}"},
            json={
                "personalizations": [{"to": [{"email": owner_email}]}],
                "from": {"email": "bookings@bookslot.app"},
                "subject": "New Booking Received",
                "content": [{"type": "text/plain", "value": f"Booking details: {booking_details}"}]
            }
        )
    
    # 2. Trigger WhatsApp via Twilio
    twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
    twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
    twilio_number = os.getenv('TWILIO_WHATSAPP_NUMBER')
    
    if twilio_sid and twilio_token and owner_phone:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json",
                auth=(twilio_sid, twilio_token),
                data={
                    "From": f"whatsapp:{twilio_number}",
                    "To": f"whatsapp:{owner_phone}",
                    "Body": f"New Booking! {booking_details['customer']} at {booking_details['time']}."
                }
            )