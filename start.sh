#!/bin/bash
cd backend
pip install --upgrade pip
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port $PORT