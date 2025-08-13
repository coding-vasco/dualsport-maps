# Simple Dockerfile for Render deployment
FROM python:3.11-slim

WORKDIR /app

# Copy backend files
COPY backend/ ./

# Install dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Expose port
EXPOSE 8000

# Start the application using a shell script to properly expand environment variables
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]