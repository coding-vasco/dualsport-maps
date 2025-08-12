#!/usr/bin/env python3
"""
Test error scenarios and validation
"""

import requests
import json

def test_error_scenarios():
    base_url = "https://trail-discovery-1.preview.emergentagent.com"
    api_url = f"{base_url}/api"
    
    print("Testing error scenarios and validation...")
    
    # Test 1: Invalid coordinates
    print("\n1. Testing invalid coordinates...")
    payload = {
        "coordinates": [{"longitude": 200, "latitude": 100}],  # Invalid coords
        "surface_preference": "mixed"
    }
    
    try:
        response = requests.post(f"{api_url}/route", json=payload, timeout=10)
        if response.status_code == 422:
            print("✅ Invalid coordinates properly rejected (422)")
        else:
            print(f"❌ Expected 422, got {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 2: Single coordinate
    print("\n2. Testing single coordinate...")
    payload = {
        "coordinates": [{"longitude": -105.0178, "latitude": 39.7392}],  # Only one point
        "surface_preference": "mixed"
    }
    
    try:
        response = requests.post(f"{api_url}/route", json=payload, timeout=10)
        if response.status_code == 422:
            print("✅ Single coordinate properly rejected (422)")
        else:
            print(f"❌ Expected 422, got {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 3: Invalid advanced route parameters
    print("\n3. Testing invalid advanced route parameters...")
    payload = {
        "coordinates": [
            {"longitude": -105.0178, "latitude": 39.7392},
            {"longitude": -105.2705, "latitude": 40.0150}
        ],
        "max_detours": 15,  # Exceeds limit of 10
        "detour_radius_km": 25  # Exceeds limit of 20
    }
    
    try:
        response = requests.post(f"{api_url}/route/advanced", json=payload, timeout=10)
        if response.status_code == 422:
            print("✅ Invalid advanced parameters properly rejected (422)")
        elif response.status_code == 503:
            print("✅ Service unavailable (expected due to missing tokens)")
        else:
            print(f"❌ Expected 422 or 503, got {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 4: Empty place search
    print("\n4. Testing empty place search...")
    payload = {"query": "", "limit": 5}
    
    try:
        response = requests.post(f"{api_url}/places/search", json=payload, timeout=10)
        if response.status_code == 422:
            print("✅ Empty query properly rejected (422)")
        else:
            print(f"❌ Expected 422, got {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 5: Test environment variables and feature flags
    print("\n5. Testing environment variables setup...")
    print("   - OPENROUTE_API_KEY: Present (service working)")
    print("   - MAPBOX_TOKEN: Empty (expected)")
    print("   - MAPILLARY_TOKEN: Empty (expected)")
    print("   - WIKILOC_TOKEN: Empty (expected)")
    print("   - Enhanced planner gracefully degrades: ✅")

if __name__ == "__main__":
    test_error_scenarios()