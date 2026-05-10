from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from . import i18n_config

app = FastAPI()

@app.middleware("http")
async def add_locale_middleware(request: Request, call_next):
    locale = request.query_params.get("lang", "en")
    request.state.locale = locale
    # Update templates environment with the locale
    request.state.templates = Jinja2Templates(directory="templates")
    request.state.templates.env = i18n_config.get_jinja_env(locale=locale)
    
    response = await call_next(request)
    return response