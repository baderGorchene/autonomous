#!/bin/bash

echo "Installing security scanning tools..."
pip install bandit safety

echo "Running Bandit static analysis..."
bandit -r src/ -ll -f txt -o bandit_report.txt

echo "Running Safety dependency vulnerability scan..."
safety scan -r requirements.txt --full-report --output safety_report.json

echo "Security scans completed. Check bandit_report.txt and safety_report.json for results."
