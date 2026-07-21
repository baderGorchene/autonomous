from jinja2 import Environment, FileSystemLoader
from jinja2.ext import i18n
import gettext
import os

def get_jinja_env(locale='en', templates_dir='templates', project_root=None):
    if project_root is None:
        current_dir = os.path.dirname(__file__)
        project_root = os.path.abspath(os.path.join(current_dir, os.pardir))

    env = Environment(loader=FileSystemLoader(templates_dir), extensions=[i18n])
    
    localedir = os.path.join(project_root, 'locales')
    
    translate = gettext.translation('messages', localedir, languages=[locale], fallback=True)
    env.install_gettext_translations(translate)
    
    return env
