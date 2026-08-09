import gettext
from functools import lru_cache
from typing import Callable

@lru_cache(maxsize=None)
def get_translator(lang: str) -> Callable[[str], str]:
    try:
        localedir = "locales"
        t = gettext.translation("messages", localedir, languages=[lang], fallback=True)
        return t.gettext
    except Exception:
        # Fallback to default gettext if translation files are missing or an error occurs
        print(f"Warning: Could not load translation for language '{lang}'. Falling back to default.")
        return gettext.gettext

def set_language(request, lang: str):
    request.session["lang"] = lang

def get_language(request) -> str:
    return request.session.get("lang", "en")
