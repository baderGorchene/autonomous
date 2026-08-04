from babel import Locale
from babel.messages.pofile import read_po
from babel.messages.catalog import Catalog
import os
from threading import local
from src.config import settings
import logging

logger = logging.getLogger(__name__)

_tlocal = local()

def get_locale() -> str:
    """Get the current locale from the thread-local storage."""
    return getattr(_tlocal, 'locale', 'en')

def set_locale(locale_code: str):
    """Set the current locale in the thread-local storage."""
    _tlocal.locale = locale_code

def get_translations(locale_code: str) -> Catalog:
    """Load translations for a given locale."""
    catalog = Catalog(locale=locale_code)
    locale_dir = os.path.join(settings.LOCALES_DIR, locale_code, 'LC_MESSAGES')
    po_file_path = os.path.join(locale_dir, 'messages.po')

    if os.path.exists(po_file_path):
        try:
            with open(po_file_path, 'rb') as f:
                catalog = read_po(f, locale=locale_code)
        except Exception as e:
            logger.error(f"Error loading translation file {po_file_path}: {e}")
    else:
        logger.warning(f"Translation file not found for locale {locale_code} at {po_file_path}")
    return catalog

# Cache for loaded catalogs
_catalogs = {}

def get_catalog(locale_code: str) -> Catalog:
    if locale_code not in _catalogs:
        _catalogs[locale_code] = get_translations(locale_code)
    return _catalogs[locale_code]

def _(text: str, locale_code: Optional[str] = None) -> str:
    """Translate a given text based on the current or specified locale."""
    if locale_code is None:
        locale_code = get_locale()

    if locale_code == 'en': # No need to translate if it's the source language
        return text

    catalog = get_catalog(locale_code)
    translation = catalog.get(text)
    return translation if translation is not None else text
