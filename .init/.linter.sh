#!/bin/bash
set -euo pipefail

cd /home/kavia/workspace/code-generation/resident-directory-management-system-303803-303821/resident_directory_backend

# CI images may not have dependencies installed (including flake8). Install from requirements.txt.
# Non-interactive and idempotent for CI.
python -m pip install --disable-pip-version-check --no-input -r requirements.txt

python -m flake8 .

