from jinja2 import Environment, FileSystemLoader
from jinja2.ext import i18n
import gettext
import os
import logging
from src.config import settings
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from fastapi.templating import Jinja2Templates # Import Jinja2Templates

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(settings.PROJECT_ROOT, 'templates')
LOCALES_DIR = settings.LOCALES_DIR

# Cache for Jinja2Templates instances
_templates_cache = {}

def get_jinja_templates(locale='en'):
    if locale in _templates_cache:
        return _templates_cache[locale]

    # Create a Jinja2 Environment first
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), extensions=[i18n])
    
    if not os.path.exists(LOCALES_DIR):
        logger.warning(f"Locales directory not found at {LOCALES_DIR}")
        translate = gettext.NullTranslations()
    else:
        try:
            translate = gettext.translation('messages', LOCALES_DIR, languages=[locale], fallback=True)
        except Exception as e:
            logger.warning(f"Could not load translations for locale '{locale}': {e}")
            translate = gettext.NullTranslations()
            
    env.install_gettext_translations(translate)
    
    # Add a custom filter to update a specific query parameter in a URL
    # This is different from the standard 'urlencode' which encodes a dict to a query string.
    def update_query_param_filter(url, query_param_name, value):
        parsed_url = urlparse(str(url)) # Ensure URL is string
        query_params = parse_qs(parsed_url.query)
        query_params[query_param_name] = [value]
        new_query = urlencode(query_params, doseq=True)
        return urlunparse(parsed_url._replace(query=new_query))

    env.filters['update_query_param'] = update_query_param_filter

    # Add a custom filter for currency formatting
    def format_currency_filter(value, lang_code, currency_code="USD"):
        # This is a simplified example. For full i18n currency formatting,
        # you'd use a library like Babel or a more robust custom implementation.
        try:
            numeric_value = float(value)
            if lang_code == 'ar':
                # Example for Arabic, assuming SAR for now
                return f"{numeric_value:,.2f} \u0631.\u0633"
            elif lang_code == 'fr':
                # Example for French, assuming EUR
                return f"{numeric_value:,.2f} \u20ac"
            else:
                return f"${numeric_value:,.2f}"
        except (ValueError, TypeError):
            return str(value) # Return original value if not a valid number

    env.filters['format_currency'] = format_currency_filter

    # Create and cache Jinja2Templates instance
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    templates.env = env # Override the default env with our configured one
    _templates_cache[locale] = templates
    
    return templates

# Dependency to get Jinja2Templates instance with current locale
def get_templates_env(request):
    return get_jinja_templates(request.state.lang)
