#!/bin/bash
echo "Compiling .po files to .mo files..."
# The locales directory is located at src/locales based on src/i18n_config.py
pybabel compile -D messages -d src/locales
if [ $? -eq 0 ]; then
    echo "Translation files compiled successfully."
else
    echo "Error compiling translation files."
    exit 1
fi