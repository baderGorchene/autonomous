from babel.support import Translations
import os

_translations_cache = {}

def get_translator(locale: str):
    if locale not in _translations_cache:
        locale_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'locales')
        try:
            _translations_cache[locale] = Translations.load(locale_dir, [locale])
        except Exception as e:
            print(f"Warning: Could not load translations for locale {locale}: {e}. Falling back to default.")
            _translations_cache[locale] = Translations() # Fallback to a dummy translator
    return _translations_cache[locale].gettext
