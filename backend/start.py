#!/usr/bin/env python3
"""
Production startup script for DUALSPORT MAPS backend
"""

import os
import sys
import uvicorn
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

def main():
    """Start the FastAPI application with production settings"""
    
    # Get port from environment (Render sets this automatically)
    port = int(os.environ.get("PORT", 8000))
    
    # Get host (0.0.0.0 for production)
    host = os.environ.get("HOST", "0.0.0.0")
    
    # Determine if we're in production
    is_production = os.environ.get("RENDER") is not None
    
    # Configure uvicorn settings
    uvicorn_config = {
        "app": "server:app",
        "host": host,
        "port": port,
        "workers": 1 if not is_production else 2,  # Scale based on environment
        "access_log": True,
        "log_level": "info" if is_production else "debug",
    }
    
    print(f"🚀 Starting DUALSPORT MAPS backend on {host}:{port}")
    print(f"📍 Production mode: {is_production}")
    print(f"🔧 Workers: {uvicorn_config['workers']}")
    
    # Start the server
    uvicorn.run(**uvicorn_config)

if __name__ == "__main__":
    main()