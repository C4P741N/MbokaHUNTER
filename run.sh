#!/usr/bin/env bash

clear

docker compose down 
docker compose up -d --build
#python3 -m debugpy --listen 0.0.0.0:5678 --wait-for-client main.py
