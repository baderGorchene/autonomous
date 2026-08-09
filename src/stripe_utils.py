import stripe
import logging
from .config import settings

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_checkout_session(owner_id: int, owner_email: str, success_url: str, cancel_url: str):
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
            metadata={
                'owner_id': str(owner_id),
            }
        )
        return checkout_session
    except stripe.error.StripeError as e:
        logger.error(f"Error creating Stripe checkout session: {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during Stripe checkout session creation: {e}")
        raise

def handle_webhook_event(payload: bytes, sig_header: str):
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        return event
    except ValueError as e:
        # Invalid payload
        logger.error(f"Stripe webhook error: Invalid payload: {e}")
        raise
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Stripe webhook error: Invalid signature: {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during Stripe webhook handling: {e}")
        raise
