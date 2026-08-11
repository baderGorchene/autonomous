#!/bin/bash

echo "Running pip-audit for dependency vulnerabilities..."
pip-audit -r requirements.txt

echo ""
echo "Running Bandit for static application security testing..."
# Bandit can be configured with a .bandit file or command-line args.
# For now, a basic scan of the src directory.
bandit -r src -ll -f custom --msg-template "{abspath}:{line}:{col}: {severity}: {test_id}: {msg}"
