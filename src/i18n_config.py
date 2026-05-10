from jinja2 import Environment, FileSystemLoader
from jinja2.ext import i18n
import gettext
import os

def get_jinja_env(locale='en'):
    env = Environment(loader=FileSystemLoader('templates'), extensions=[i18n])
    
    # Setup gettext translations
    localedir = os.path.join(os.path.dirname(__file__), 'locales')
    translate = gettext.translation('messages', localedir, languages=[locale], fallback=True)
    env.install_gettext_translations(translate)
    
    return env