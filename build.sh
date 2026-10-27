#!/usr/bin/env bash
# Build step used by Render (and handy locally). Run from the project root: bash build.sh
set -o errexit

echo "==> Installing Python packages"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "==> Building the web interface"
cd frontend
if [ -f package-lock.json ]; then npm ci; else npm install; fi
npm run build
cd ..

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Build finished"
