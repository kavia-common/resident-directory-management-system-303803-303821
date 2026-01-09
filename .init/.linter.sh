#!/bin/bash
cd /home/kavia/workspace/code-generation/resident-directory-management-system-303803-303821/resident_directory_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

