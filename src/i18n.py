import os
import gettext
from fastapi import Request
from .config import settings

# Setup gettext
localedir = settings.LOCALES_DIR
DEFAULT_LOCALE = settings.DEFAULT_LOCALE

def get_translator(locale: str):
    try:
        # Bind the domain 'messages' to the locale directory
        t = gettext.translation('messages', localedir, languages=[locale], fallback=True)
        t.install()
        return t.gettext
    except FileNotFoundError:
        # Fallback to default if locale not found
        t = gettext.translation('messages', localedir, languages=[DEFAULT_LOCALE], fallback=True)
        t.install()
        return t.gettext

# Global _ for convenience, will be set by middleware
_ = gettext.gettext

def get_locale(request: Request) -> str:
    # Try to get locale from cookie, header, or query param
    locale = request.cookies.get("locale") or request.headers.get("Accept-Language", "").split(',')[0].split('-')[0]
    if not locale or locale not in ["en", "ar", "fr"]: # Add supported locales
        locale = DEFAULT_LOCALE
    return locale

@DeprecationWarning("This function is deprecated. Use the `_` provided by the middleware after `get_translator(request.state.locale)` has been called.")
def gettext_lazy(message: str) -> str:
    """
    A lazy gettext function that can be used for strings that are defined at module load time
    but whose translation depends on the request's locale.
    In a FastAPI context, this is often handled by middleware setting the global `_` or
    passing the translator object. For simplicity, we'll rely on the middleware.
    """
    return message
