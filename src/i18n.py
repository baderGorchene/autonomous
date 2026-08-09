import gettext as _gettext
from fastapi import Request, Depends, Header
from typing import Optional
from .config import settings

# Initialize gettext translations
_gettext.bindtextdomain('messages', settings.LOCALES_DIR)
_gettext.textdomain('messages')

def gettext(locale: str):
    """Returns the translation function for a given locale."""
    try:
        return _gettext.translation('messages', settings.LOCALES_DIR, languages=[locale]).gettext
    except _gettext.TranslationError:
        # Fallback to default locale if requested locale is not found
        return _gettext.translation('messages', settings.LOCALES_DIR, languages=[settings.DEFAULT_LOCALE]).gettext

def _(message: str) -> str:
    """Default translation function using the default locale."""
    return gettext(settings.DEFAULT_LOCALE)(message)

def get_locale(request: Request, accept_language: Optional[str] = Header(None)) -> str:
    """
    Determines the locale based on query parameter, cookie, or Accept-Language header.
    Defaults to settings.DEFAULT_LOCALE.
    """
    # 1. Check query parameter
    if "lang" in request.query_params:
        return request.query_params["lang"]

    # 2. Check cookie
    if "lang" in request.cookies:
        return request.cookies["lang"]

    # 3. Check Accept-Language header
    if accept_language:
        # Parse header, e.g., "en-US,en;q=0.9,ar;q=0.8"
        # Take the first language or more preferred one
        preferred_languages = [lang.split(';')[0].strip().split('-')[0] for lang in accept_language.split(',')]
        for lang in preferred_languages:
            if lang in ['en', 'ar', 'fr']: # Supported languages
                return lang

    # 4. Fallback to default
    return settings.DEFAULT_LOCALE

# Add a Jinja2 filter for currency formatting with locale
def format_currency(value: float, currency_code: str, locale: str) -> str:
    """
    Formats a currency value based on locale.
    Note: For production, consider a more robust library like `babel`.
    This is a simplified implementation.
    """
    if locale == 'ar':
        # Example for Arabic (right-to-left, currency symbol usually after number)
        # This is a very basic example and might not cover all nuances.
        # For actual production, use a dedicated i18n library.
        if currency_code == "SAR":
            return f"{value:,.2f} ر.س" # Saudi Riyal
        elif currency_code == "AED":
            return f"{value:,.2f} د.إ" # UAE Dirham
        else: # Fallback for other currencies
            return f"{value:,.2f} {currency_code}"
    elif locale == 'fr':
        # Example for French (comma as decimal separator, space for thousands)
        # This is a very basic example and might not cover all nuances.
        return f"{value:,.2f} {currency_code}".replace(",", "X").replace(".", ",").replace("X", ".")
    else: # Default to English style
        return f"{currency_code} {value:,.2f}"
