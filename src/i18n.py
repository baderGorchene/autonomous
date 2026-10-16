from babel.support import Translations
import os

_current_locale = 'en'
_translations_cache = {}

TRANSLATIONS_DICT = {
    "ar": {
        "Login": "تسجيل الدخول",
        "Email": "البريد الإلكتروني",
        "Email Address": "البريد الإلكتروني",
        "Password": "كلمة المرور",
        "Welcome": "أهلاً",
        "Upcoming Bookings": "الحجوزات القادمة",
        "Upcoming Appointments": "الحجوزات القادمة",
        "Book an Appointment with": "احجز موعداً مع",
        "Select a Service": "اختر خدمة",
        "Select Service": "اختر خدمة",
        "Monday": "الاثنين",
        "Tuesday": "الثلاثاء",
        "Wednesday": "الأربعاء",
        "Thursday": "الخميس",
        "Friday": "الجمعة",
        "Saturday": "السبت",
        "Sunday": "الأحد",
    },
    "fr": {
        "Login": "Connexion",
        "Email": "E-mail",
        "Email Address": "E-mail",
        "Password": "Mot de passe",
        "Welcome": "Bienvenue",
        "Upcoming Bookings": "Prochaines réservations",
        "Upcoming Appointments": "Prochaines réservations",
        "Book an Appointment with": "Prendre rendez-vous avec",
        "Select a Service": "Sélectionnez un service",
        "Select Service": "Sélectionnez un service",
        "Monday": "Lundi",
        "Tuesday": "Mardi",
        "Wednesday": "Mercredi",
        "Thursday": "Jeudi",
        "Friday": "Vendredi",
        "Saturday": "Samedi",
        "Sunday": "Dimanche",
    }
}

def set_locale(locale: str):
    global _current_locale
    _current_locale = locale

def get_locale() -> str:
    return _current_locale

def get_translator(locale: str = None):
    if locale is None:
        locale = _current_locale
    
    locale_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'locales')
    babel_gettext = None
    if locale not in _translations_cache:
        try:
            _translations_cache[locale] = Translations.load(locale_dir, [locale])
        except Exception:
            _translations_cache[locale] = Translations()
    
    babel_gettext = _translations_cache[locale].gettext

    def custom_gettext(message: str) -> str:
        if not message:
            return ""
        str_msg = str(message)
        # Check explicit overrides
        if locale in TRANSLATIONS_DICT and str_msg in TRANSLATIONS_DICT[locale]:
            return TRANSLATIONS_DICT[locale][str_msg]
        res = babel_gettext(str_msg)
        if res and res != str_msg:
            return res
        return str_msg

    return custom_gettext
