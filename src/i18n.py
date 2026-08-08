import gettext
from functools import lru_cache
from typing import Optional

_translation = None

def init_i18n(locales_dir: str, default_locale: str):
    """Initializes the gettext translation system."""
    _set_translation_for_locale(default_locale, locales_dir)

def _set_translation_for_locale(locale: str, locales_dir: str):
    """Helper to set up gettext translation for a specific locale."""
    global _translation
    try:
        _translation = gettext.translation('messages', locales_dir, languages=[locale], fallback=True)
        _translation.install()
    except FileNotFoundError:
        print(f"Warning: Locale directory {locales_dir} not found or messages.mo missing for {locale}. Falling back to default strings.")
        _translation = None

def gettext_lazy(message: str):
    """A lazy gettext function."""
    if _translation:
        return _translation.gettext(message)
    return message

def ngettext_lazy(singular: str, plural: str, n: int):
    """A lazy ngettext function."""
    if _translation:
        return _translation.ngettext(singular, plural, n)
    return singular if n == 1 else plural

@lru_cache(maxsize=128)
def _format_currency_en(price: float) -> str:
    return f"${price:,.2f}"

@lru_cache(maxsize=128)
def _format_currency_ar(price: float) -> str:
    # This is a simplified example. For real world, use locale-aware libraries.
    return f"{price:,.2f} د.إ" # Assuming AED for MENA region

@lru_cache(maxsize=128)
def _format_currency_fr(price: float) -> str:
    return f"{price:,.2f} €" # Assuming Euro for French

def gettext_filter(text: str, **kwargs) -> str:
    """Jinja2 filter for gettext, supporting currency formatting."""
    locale = kwargs.get('locale', 'en') # Default to 'en' if not provided
    
    if text == "currency_format":
        price = kwargs.get('price')
        if price is None:
            return ""
        if locale == "ar":
            return _format_currency_ar(price)
        elif locale == "fr":
            return _format_currency_fr(price)
        else: # Default to English
            return _format_currency_en(price)
    
    if _translation:
        return _translation.gettext(text)
    return text

def get_locale() -> str:
    """Returns the current active locale. This function would ideally be context-aware (e.g., request-scoped)."""
    # In a real FastAPI app, this would be dynamically set per request via middleware.
    # For this reconstruction, we'll assume the _translation object's language implies the locale.
    if _translation and hasattr(_translation, '_info') and 'language' in _translation._info:
        return _translation._info['language']
    return "en" # Fallback to default
