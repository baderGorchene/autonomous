from babel.numbers import format_currency
from src.i18n import get_locale

def format_currency_filter(value: float, currency_code: str = "USD") -> str:
    """Jinja2 filter to format currency based on the current locale."""
    current_locale = get_locale()
    try:
        return format_currency(value, currency_code, locale=current_locale)
    except Exception as e:
        # Fallback in case of error, e.g., invalid locale or currency code
        print(f"Error formatting currency for locale {current_locale}: {e}")
        return f"{currency_code} {value:,.2f}"
