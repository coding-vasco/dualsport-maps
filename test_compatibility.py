#!/usr/bin/env python3
"""
Quick test for backward compatibility endpoints
"""

import requests
import json

def test_endpoints():
    base_url = "https://trail-discovery-1.preview.emergentagent.com"
    api_url = f"{base_url}/api"
    
    # Test coordinates: Denver to Boulder
    test_coordinates = [
        {"longitude": -105.0178, "latitude": 39.7392},  # Denver
        {"longitude": -105.2705, "latitude": 40.0150}   # Boulder
    ]
    
    # Test 1: Root endpoint
    print("1. Testing root endpoint...")
    try:
        response = requests.get(f"{api_url}/", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "DUALSPORT MAPS" in data.get('message', ''):
                print("✅ Root endpoint working")
            else:
                print(f"❌ Root endpoint missing branding: {data}")
        else:
            print(f"❌ Root endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Root endpoint error: {e}")
    
    # Test 2: Rate limit status
    print("\n2. Testing rate limit status...")
    try:
        response = requests.get(f"{api_url}/rate-limit-status", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'daily_count' in data and 'daily_limit' in data:
                print(f"✅ Rate limit status working - {data['requests_remaining']}/{data['daily_limit']} remaining")
            else:
                print(f"❌ Rate limit status missing fields: {data}")
        else:
            print(f"❌ Rate limit status failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Rate limit status error: {e}")
    
    # Test 3: Legacy route endpoint
    print("\n3. Testing legacy route endpoint...")
    payload = {
        "coordinates": test_coordinates,
        "surface_preference": "mixed",
        "technical_difficulty": "moderate",
        "avoid_highways": True,
        "output_format": "geojson"
    }
    
    try:
        response = requests.post(f"{api_url}/route", json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if 'route' in data and 'distance' in data:
                print(f"✅ Legacy route working - {data['distance']:.0f}m, {data['duration']:.0f}s")
            else:
                print(f"❌ Legacy route missing fields: {list(data.keys())}")
        elif response.status_code == 429:
            print("⚠️ Legacy route rate limited")
        else:
            print(f"❌ Legacy route failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data.get('detail', 'Unknown')}")
            except:
                pass
    except Exception as e:
        print(f"❌ Legacy route error: {e}")
    
    # Test 4: Enhanced route endpoint
    print("\n4. Testing enhanced route endpoint...")
    enhanced_payload = {
        **payload,
        "poi_types": ["fuel", "restaurant"],
        "max_detours": 2,
        "include_pois": True,
        "include_dirt_segments": True,
        "detour_radius_km": 5.0
    }
    
    try:
        response = requests.post(f"{api_url}/route/enhanced", json=enhanced_payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if 'route' in data and 'enhancements' in data:
                enhancements = data['enhancements']
                print(f"✅ Enhanced route working - POIs: {len(enhancements.get('pois', []))}, Dirt: {len(enhancements.get('dirt_segments', []))}")
            else:
                print(f"❌ Enhanced route missing fields: {list(data.keys())}")
        elif response.status_code == 429:
            print("⚠️ Enhanced route rate limited")
        else:
            print(f"❌ Enhanced route failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data.get('detail', 'Unknown')}")
            except:
                pass
    except Exception as e:
        print(f"❌ Enhanced route error: {e}")
    
    # Test 5: Places search
    print("\n5. Testing places search...")
    search_payload = {"query": "Denver, CO", "limit": 3}
    
    try:
        response = requests.post(f"{api_url}/places/search", json=search_payload, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                print(f"✅ Places search working - found {len(data)} places")
            else:
                print(f"❌ Places search no results: {data}")
        elif response.status_code == 429:
            print("⚠️ Places search rate limited")
        else:
            print(f"❌ Places search failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Places search error: {e}")

if __name__ == "__main__":
    test_endpoints()