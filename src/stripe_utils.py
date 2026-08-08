import stripe
from src.config import settings
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_checkout_session(
    owner_id: int,
    owner_email: str,
    success_url: str,
    cancel_url: str
) -> str:
    """
    Creates a Stripe Checkout Session for a one-time subscription payment.
    Returns the URL to redirect the customer.
    """
    if not settings.STRIPE_PRODUCT_ID or not settings.STRIPE_PRICE_ID:
        logger.error("Stripe PRODUCT_ID or PRICE_ID not configured.")
        raise HTTPException(status_code=500, detail="Stripe product not configured.")

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': settings.STRIPE_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=owner_email,
            client_reference_id=str(owner_id),
            metadata={
                'owner_id': str(owner_id)
            }
        )
        return checkout_session.url
    except stripe.error.StripeError as e:
        logger.error(f"Error creating Stripe checkout session: {e}")
        raise HTTPException(status_code=500, detail=f"Stripe error: {e.user_message}")
    except Exception as e:
        logger.error(f"Unexpected error creating Stripe checkout session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session.")

def handle_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    """
    Handles and verifies a Stripe webhook event.
    """
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        return event
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Unexpected error handling webhook: {e}")
        raise HTTPException(status_code=500, detail="Failed to process webhook event.")
