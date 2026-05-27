#!/bin/bash
# Deploy frontend after git pull
set -e
cd /home/ozonpro/app
echo 'Pulling latest changes...'
git pull origin main
echo 'Building frontend container...'
docker compose up -d --build frontend
echo 'Done! Check: http://135.106.158.198/'
docker compose ps frontend
