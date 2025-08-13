# Simple Dockerfile for Render deployment
FROM python:3.11-slim

WORKDIR /app

# Copy backend files
COPY backend/ ./

# Install dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Expose port
EXPOSE $PORT

# Start the application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "$PORT"]