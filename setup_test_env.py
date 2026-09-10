import subprocess
import sys

def main():
    print("Installing test dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pytest", "pytest-cov", "httpx", "fastapi", "sqlalchemy", "pydantic", "pydantic-settings", "jinja2"])
    print("Dependencies installed successfully.")

if __name__ == "__main__":
    main()
