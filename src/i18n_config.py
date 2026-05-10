from jinja2 import Environment
from jinja2.ext import i18n
import gettext

def get_jinja_env():
    env = Environment(extensions=[i18n])
    # In a production app, load locale files here
    env.install_null_translations()
    return env