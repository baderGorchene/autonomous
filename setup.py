from setuptools import setup, find_packages

setup(
    name="bookslot",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "pydantic",
        "pydantic-settings",
        "jinja2",
        "python-multipart",
        "pytest",
        "requests"
    ],
)
