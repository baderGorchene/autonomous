from gettext import translation, bindtextdomain, textdomain, gettext as _gettext, ngettext as _ngettext
from gettext import gettext_lazy, ngettext_lazy
from typing import Callable, Dict
from starlette.requests import Request
from src.config import settings

# A dictionary to store pre-loaded translation objects
_translations: Dict[str, translation] = {}
_default_translation: translation = None

def init_i18n(locales_dir: str, default_locale: str):
    global _default_translation
    bindtextdomain('messages', locales_dir)
    textdomain('messages')
    # Set the codeset for the textdomain
    _gettext.bind_textdomain_codeset('messages', 'utf-8')

    # Pre-load translations for supported languages
    supported_languages = ['en', 'ar', 'fr'] # Explicitly define supported languages
    for lang in supported_languages:
        try:
            _translations[lang] = translation('messages', localedir=locales_dir, languages=[lang])
            _translations[lang].install() # Install for the current thread
        except FileNotFoundError:
            print(f"Warning: Translation file not found for language '{lang}' in '{locales_dir}'")
            # Fallback to a dummy translation object that just returns the original string
            class DummyTranslation:
                def gettext(self, message): return message
                def ngettext(self, singular, plural, n): return singular if n==1 else plural
            _translations[lang] = DummyTranslation()

    _default_translation = _translations.get(default_locale)
    if _default_translation is None:
        # If default_locale itself is not found, fallback to basic gettext
        class FallbackTranslation:
            def gettext(self, message): return message
            def ngettext(self, singular, plural, n): return singular if n==1 else plural
        _default_translation = FallbackTranslation()
    _translations['default'] = _default_translation # Fallback if specific locale not found in request

def get_locale(request: Request) -> str:
    # 1. From session (user preference)
    session_lang = request.session.get("lang")
    if session_lang in _translations:
        return session_lang

    # 2. From Accept-Language header
    accept_language = request.headers.get("accept-language")
    if accept_language:
        for lang_code in accept_language.split(','):
            lang = lang_code.split(';')[0].strip().lower()
            # Check for exact match or general family
            if lang.startswith('en'): return 'en'
            if lang.startswith('ar'): return 'ar'
            if lang.startswith('fr'): return 'fr'

    # 3. Fallback to default from settings
    return settings.DEFAULT_LOCALE

def gettext_for_locale(locale: str) -> Callable[[str], str]:
    """Returns the gettext function for a specific locale."""
    return _translations.get(locale, _default_translation).gettext

# Expose global gettext and ngettext for module-level use (e.g., schemas, models)
# These will use the default domain/locale set by init_i18n
gettext = _gettext
ngettext = _ngettext
