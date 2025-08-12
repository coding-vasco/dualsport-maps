#!/usr/bin/env python3
"""
Quick test for the new advanced route endpoint
"""

import requests
import json

def test_advanced_route():
    base_url = "https://trail-discovery-1.preview.emergentagent.com"
    api_url = f"{base_url}/api"
    
    # Test coordinates: Denver to Boulder (from review request)
    test_coordinates = [
        {"longitude": -105.0178, "latitude": 39.7392},  # Denver
        {"longitude": -105.2705, "latitude": 40.0150}   # Boulder
    ]
    
    payload = {
        "coordinates": test_coordinates,
        "surface_preference": "mixed",
        "technical_difficulty": "moderate",
        "avoid_highways": True,
        "avoid_primary": False,
        "avoid_trunk": True,
        "output_format": "geojson",
        "include_instructions": True,
        "include_elevation": True,
        "max_detours": 3,
        "detour_radius_km": 5.0,
        "include_pois": True,
        "include_dirt_segments": True
    }
    
    print("Testing /api/route/advanced endpoint...")
    print(f"URL: {api_url}/route/advanced")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(f"{api_url}/route/advanced", json=payload, timeout=30)
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS - Response structure:")
            print(f"  - route_options: {len(data.get('route_options', []))} options")
            print(f"  - diagnostics: {list(data.get('diagnostics', {}).keys())}")
            print(f"  - stats: {list(data.get('stats', {}).keys())}")
            print(f"  - generated_at: {data.get('generated_at', 'N/A')}")
            
            if data.get('route_options'):
                first_option = data['route_options'][0]
                print(f"  - First option: {first_option.get('name', 'N/A')} ({first_option.get('confidence', 0):.2f} confidence)")
            
        elif response.status_code == 503:
            print("✅ EXPECTED - Service unavailable (missing API tokens)")
            try:
                error_data = response.json()
                print(f"  - Detail: {error_data.get('detail', 'N/A')}")
            except:
                pass
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            try:
                error_data = response.json()
                print(f"  - Error: {error_data}")
            except:
                print(f"  - Response: {response.text[:200]}")
                
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")

if __name__ == "__main__":
    test_advanced_route()