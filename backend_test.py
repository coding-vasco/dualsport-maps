#!/usr/bin/env python3
"""
Backend API Test Suite for ADV Route Planner
Tests all API endpoints including place search, route calculation, and rate limiting.
"""

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

class ADVRoutePlannerTester:
    def __init__(self, base_url="https://7971830f-0da5-4d30-93fa-9fc16aee00a4.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED {details}")
        else:
            print(f"❌ {name} - FAILED {details}")

    def test_root_endpoint(self) -> bool:
        """Test the root API endpoint"""
        try:
            response = self.session.get(f"{self.api_url}/")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = "message" in data
                details = f"- Status: {response.status_code}, Message: {data.get('message', 'N/A')}"
            else:
                details = f"- Status: {response.status_code}"
                
            self.log_test("Root API Endpoint", success, details)
            return success
            
        except Exception as e:
            self.log_test("Root API Endpoint", False, f"- Error: {str(e)}")
            return False

    def test_rate_limit_status(self) -> bool:
        """Test rate limit status endpoint"""
        try:
            response = self.session.get(f"{self.api_url}/rate-limit-status")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                required_fields = ['daily_count', 'daily_limit', 'requests_remaining', 'can_make_request']
                success = all(field in data for field in required_fields)
                details = f"- Remaining: {data.get('requests_remaining', 'N/A')}/{data.get('daily_limit', 'N/A')}"
            else:
                details = f"- Status: {response.status_code}"
                
            self.log_test("Rate Limit Status", success, details)
            return success
            
        except Exception as e:
            self.log_test("Rate Limit Status", False, f"- Error: {str(e)}")
            return False

    def test_place_search(self) -> bool:
        """Test place search functionality"""
        test_queries = [
            "San Francisco, CA",
            "Los Angeles, CA", 
            "Yosemite National Park",
            "New York"
        ]
        
        all_passed = True
        
        for query in test_queries:
            try:
                payload = {
                    "query": query,
                    "limit": 5
                }
                
                response = self.session.post(f"{self.api_url}/places/search", json=payload)
                success = response.status_code == 200
                
                if success:
                    data = response.json()
                    success = isinstance(data, list) and len(data) > 0
                    
                    if success and len(data) > 0:
                        # Validate structure of first result
                        first_result = data[0]
                        required_fields = ['label', 'value', 'coordinates']
                        success = all(field in first_result for field in required_fields)
                        
                        if success:
                            coords = first_result['coordinates']
                            success = 'latitude' in coords and 'longitude' in coords
                            details = f"- Found {len(data)} places for '{query}'"
                        else:
                            details = f"- Missing required fields in result"
                    else:
                        details = f"- No results for '{query}'"
                else:
                    details = f"- Status: {response.status_code}"
                    
                self.log_test(f"Place Search: {query}", success, details)
                if not success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Place Search: {query}", False, f"- Error: {str(e)}")
                all_passed = False
                
        return all_passed

    def test_route_calculation(self) -> bool:
        """Test route calculation with different configurations"""
        
        # Test coordinates: San Francisco to Los Angeles
        test_coordinates = [
            {"longitude": -122.4194, "latitude": 37.7749},  # San Francisco
            {"longitude": -118.2437, "latitude": 34.0522}   # Los Angeles
        ]
        
        test_configs = [
            {
                "name": "Basic Route (Mixed Surface)",
                "config": {
                    "coordinates": test_coordinates,
                    "surface_preference": "mixed",
                    "technical_difficulty": "moderate",
                    "avoid_highways": True,
                    "avoid_primary": False,
                    "avoid_trunk": True,
                    "output_format": "geojson",
                    "include_instructions": True,
                    "include_elevation": True
                }
            },
            {
                "name": "Gravel Route (Difficult)",
                "config": {
                    "coordinates": test_coordinates,
                    "surface_preference": "gravel",
                    "technical_difficulty": "difficult",
                    "avoid_highways": True,
                    "avoid_primary": True,
                    "avoid_trunk": True,
                    "output_format": "geojson",
                    "include_instructions": True,
                    "include_elevation": True
                }
            },
            {
                "name": "GPX Output Format",
                "config": {
                    "coordinates": test_coordinates,
                    "surface_preference": "paved",
                    "technical_difficulty": "easy",
                    "avoid_highways": False,
                    "avoid_primary": False,
                    "avoid_trunk": False,
                    "output_format": "gpx",
                    "include_instructions": True,
                    "include_elevation": True
                }
            }
        ]
        
        all_passed = True
        
        for test_case in test_configs:
            try:
                response = self.session.post(f"{self.api_url}/route", json=test_case["config"])
                success = response.status_code == 200
                
                if success:
                    data = response.json()
                    required_fields = ['route', 'distance', 'duration', 'waypoint_count', 'format', 'generated_at']
                    success = all(field in data for field in required_fields)
                    
                    if success:
                        # Validate route data structure
                        route_data = data['route']
                        if test_case["config"]["output_format"] == "geojson":
                            success = isinstance(route_data, dict) and 'features' in route_data
                        elif test_case["config"]["output_format"] == "gpx":
                            success = isinstance(route_data, str) and route_data.startswith('<?xml')
                        
                        details = f"- Distance: {data.get('distance', 0):.1f}m, Duration: {data.get('duration', 0):.0f}s"
                    else:
                        details = f"- Missing required fields in response"
                else:
                    details = f"- Status: {response.status_code}"
                    if response.status_code == 429:
                        details += " (Rate Limited)"
                    try:
                        error_data = response.json()
                        details += f", Error: {error_data.get('detail', 'Unknown error')}"
                    except:
                        details += f", Response: {response.text[:100]}"
                    
                self.log_test(f"Route Calculation: {test_case['name']}", success, details)
                if not success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Route Calculation: {test_case['name']}", False, f"- Error: {str(e)}")
                all_passed = False
                
        return all_passed

    def test_invalid_requests(self) -> bool:
        """Test error handling with invalid requests"""
        
        test_cases = [
            {
                "name": "Empty Place Search",
                "endpoint": "places/search",
                "method": "POST",
                "payload": {"query": "", "limit": 5},
                "expected_status": 422  # Validation error
            },
            {
                "name": "Invalid Coordinates",
                "endpoint": "route",
                "method": "POST", 
                "payload": {
                    "coordinates": [{"longitude": 200, "latitude": 100}],  # Invalid coords
                    "surface_preference": "mixed"
                },
                "expected_status": 422  # Validation error
            },
            {
                "name": "Single Coordinate Route",
                "endpoint": "route",
                "method": "POST",
                "payload": {
                    "coordinates": [{"longitude": -122.4194, "latitude": 37.7749}],  # Only one point
                    "surface_preference": "mixed"
                },
                "expected_status": 422  # Validation error
            }
        ]
        
        all_passed = True
        
        for test_case in test_cases:
            try:
                if test_case["method"] == "POST":
                    response = self.session.post(f"{self.api_url}/{test_case['endpoint']}", json=test_case["payload"])
                else:
                    response = self.session.get(f"{self.api_url}/{test_case['endpoint']}")
                
                success = response.status_code == test_case["expected_status"]
                details = f"- Expected: {test_case['expected_status']}, Got: {response.status_code}"
                
                self.log_test(f"Error Handling: {test_case['name']}", success, details)
                if not success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Error Handling: {test_case['name']}", False, f"- Error: {str(e)}")
                all_passed = False
                
        return all_passed

    def test_legacy_endpoints(self) -> bool:
        """Test legacy status check endpoints"""
        try:
            # Test creating a status check
            payload = {"client_name": f"test_client_{datetime.now().strftime('%H%M%S')}"}
            response = self.session.post(f"{self.api_url}/status", json=payload)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                required_fields = ['id', 'client_name', 'timestamp']
                success = all(field in data for field in required_fields)
                details = f"- Created status check with ID: {data.get('id', 'N/A')[:8]}..."
            else:
                details = f"- Status: {response.status_code}"
                
            self.log_test("Create Status Check", success, details)
            
            # Test getting status checks
            response = self.session.get(f"{self.api_url}/status")
            success2 = response.status_code == 200
            
            if success2:
                data = response.json()
                success2 = isinstance(data, list)
                details = f"- Retrieved {len(data)} status checks"
            else:
                details = f"- Status: {response.status_code}"
                
            self.log_test("Get Status Checks", success2, details)
            
            return success and success2
            
        except Exception as e:
            self.log_test("Legacy Endpoints", False, f"- Error: {str(e)}")
            return False

    def run_all_tests(self) -> int:
        """Run all tests and return exit code"""
        print("🚀 Starting ADV Route Planner Backend API Tests")
        print(f"📍 Testing API at: {self.api_url}")
        print("=" * 60)
        
        # Run all test suites
        test_results = [
            self.test_root_endpoint(),
            self.test_rate_limit_status(),
            self.test_place_search(),
            self.test_route_calculation(),
            self.test_invalid_requests(),
            self.test_legacy_endpoints()
        ]
        
        print("=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed! Backend API is working correctly.")
            return 0
        else:
            failed_tests = self.tests_run - self.tests_passed
            print(f"⚠️  {failed_tests} test(s) failed. Check the logs above for details.")
            return 1

def main():
    """Main test runner"""
    tester = ADVRoutePlannerTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())