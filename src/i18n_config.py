from jinja2 import Environment, FileSystemLoader
from jinja2.ext import i18n
import gettext
import os
import logging
from src.config import settings
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(settings.PROJECT_ROOT, 'templates')
LOCALES_DIR = settings.LOCALES_DIR

def get_jinja_env(locale='en'):
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
    
    def urlencode_query_param(url, query_param_name, value):
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        query_params[query_param_name] = [value]
        new_query = urlencode(query_params, doseq=True)
        return urlunparse(parsed_url._replace(query=new_query))

    env.filters['urlencode'] = urlencode_query_param
    
    return env
