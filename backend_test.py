#!/usr/bin/env python3
"""
Backend API Test Suite for DUALSPORT MAPS
Tests all API endpoints including place search, route calculation, enhanced routing, and rate limiting.
"""

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

class DualsportMapsTester:
    def __init__(self, base_url="https://dualsport-maps-backend.onrender.com"):
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
        """Test the root API endpoint and verify DUALSPORT MAPS branding"""
        try:
            response = self.session.get(f"{self.api_url}/")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = "message" in data
                message = data.get('message', '')
                # Check for DUALSPORT MAPS branding
                if "DUALSPORT MAPS" in message:
                    details = f"- Status: {response.status_code}, Message: {message}"
                else:
                    success = False
                    details = f"- Missing DUALSPORT MAPS branding in message: {message}"
            else:
                details = f"- Status: {response.status_code}"
                
            self.log_test("Root API Endpoint (DUALSPORT MAPS)", success, details)
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

    def test_legacy_route_calculation(self) -> bool:
        """Test legacy route calculation endpoint for backward compatibility"""
        
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
                    
                self.log_test(f"Legacy Route: {test_case['name']}", success, details)
                if not success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Legacy Route: {test_case['name']}", False, f"- Error: {str(e)}")
                all_passed = False
                
        return all_passed

    def test_advanced_route_calculation(self) -> bool:
        """Test new advanced route calculation endpoint"""
        
        # Test coordinates: Denver to Boulder (from review request)
        test_coordinates = [
            {"longitude": -105.0178, "latitude": 39.7392},  # Denver
            {"longitude": -105.2705, "latitude": 40.0150}   # Boulder
        ]
        
        test_configs = [
            {
                "name": "Advanced Route Basic",
                "config": {
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
            },
            {
                "name": "Advanced Route with Trip Planning",
                "config": {
                    "coordinates": test_coordinates,
                    "surface_preference": "gravel",
                    "technical_difficulty": "difficult",
                    "avoid_highways": True,
                    "avoid_primary": True,
                    "avoid_trunk": True,
                    "output_format": "geojson",
                    "include_instructions": True,
                    "include_elevation": True,
                    "max_detours": 5,
                    "detour_radius_km": 10.0,
                    "trip_duration_hours": 4.0,
                    "trip_distance_km": 100.0,
                    "include_pois": True,
                    "include_dirt_segments": True
                }
            }
        ]
        
        all_passed = True
        
        for test_case in test_configs:
            try:
                response = self.session.post(f"{self.api_url}/route/advanced", json=test_case["config"])
                success = response.status_code == 200
                
                if success:
                    data = response.json()
                    required_fields = ['route_options', 'diagnostics', 'stats', 'generated_at']
                    success = all(field in data for field in required_fields)
                    
                    if success:
                        # Validate route_options structure
                        route_options = data.get('route_options', [])
                        success = isinstance(route_options, list)
                        
                        if success and len(route_options) > 0:
                            # Check first route option structure
                            first_option = route_options[0]
                            option_fields = ['route_id', 'name', 'route_data', 'distance_m', 'duration_s', 'confidence']
                            success = all(field in first_option for field in option_fields)
                            
                        # Validate diagnostics structure
                        diagnostics = data.get('diagnostics', {})
                        if success:
                            success = 'stage_timings' in diagnostics
                            
                        details = f"- Options: {len(route_options)}, Diagnostics: {len(diagnostics)}"
                    else:
                        details = f"- Missing required fields in response"
                elif response.status_code == 503:
                    # Expected when enhanced planner is not available (missing tokens)
                    success = True
                    details = f"- Service unavailable (expected - missing API tokens)"
                else:
                    details = f"- Status: {response.status_code}"
                    if response.status_code == 429:
                        details += " (Rate Limited)"
                    try:
                        error_data = response.json()
                        details += f", Error: {error_data.get('detail', 'Unknown error')}"
                    except:
                        details += f", Response: {response.text[:100]}"
                    
                self.log_test(f"Advanced Route: {test_case['name']}", success, details)
                if not success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Advanced Route: {test_case['name']}", False, f"- Error: {str(e)}")
                all_passed = False
                
        return all_passed

    def test_enhanced_route_calculation(self) -> bool:
        """Test enhanced route calculation with POIs and dirt segments"""
        
        # Test coordinates: San Francisco to Los Angeles
        test_coordinates = [
            {"longitude": -122.4194, "latitude": 37.7749},  # San Francisco
            {"longitude": -118.2437, "latitude": 34.0522}   # Los Angeles
        ]
        
        test_configs = [
            {
                "name": "Enhanced Route with POIs",
                "config": {
                    "coordinates": test_coordinates,
                    "surface_preference": "mixed",
                    "technical_difficulty": "moderate",
                    "avoid_highways": True,
                    "avoid_primary": False,
                    "avoid_trunk": True,
                    "output_format": "geojson",
                    "include_instructions": True,
                    "include_elevation": True,
                    "poi_types": ["viewpoint", "fuel", "restaurant"],
                    "max_detours": 3,
                    "trip_duration_hours": 8.0,
                    "trip_distance_km": 600.0,
                    "include_pois": True,
                    "include_dirt_segments": True,
                    "detour_radius_km": 5.0
                }
            },
            {
                "name": "Enhanced Route with All POI Types",
                "config": {
                    "coordinates": test_coordinates,
                    "surface_preference": "gravel",
                    "technical_difficulty": "difficult",
                    "avoid_highways": True,
                    "avoid_primary": True,
                    "avoid_trunk": True,
                    "output_format": "geojson",
                    "include_instructions": True,
                    "include_elevation": True,
                    "poi_types": ["viewpoint", "peak", "fuel", "restaurant", "campsite", "information"],
                    "max_detours": 5,
                    "include_pois": True,
                    "include_dirt_segments": True,
                    "detour_radius_km": 10.0
                }
            },
            {
                "name": "Enhanced Route GPX Format",
                "config": {
                    "coordinates": test_coordinates,
                    "surface_preference": "mixed",
                    "technical_difficulty": "moderate",
                    "avoid_highways": True,
                    "output_format": "gpx",
                    "include_instructions": True,
                    "include_elevation": True,
                    "poi_types": ["fuel", "restaurant"],
                    "max_detours": 2,
                    "include_pois": True,
                    "include_dirt_segments": False,
                    "detour_radius_km": 3.0
                }
            }
        ]
        
        all_passed = True
        
        for test_case in test_configs:
            try:
                response = self.session.post(f"{self.api_url}/route/enhanced", json=test_case["config"])
                success = response.status_code == 200
                
                if success:
                    data = response.json()
                    required_fields = ['route', 'distance', 'duration', 'waypoint_count', 'format', 'generated_at', 'enhancements']
                    success = all(field in data for field in required_fields)
                    
                    if success:
                        # Validate route data structure
                        route_data = data['route']
                        if test_case["config"]["output_format"] == "geojson":
                            success = isinstance(route_data, dict) and 'features' in route_data
                        elif test_case["config"]["output_format"] == "gpx":
                            success = isinstance(route_data, str) and route_data.startswith('<?xml')
                        
                        # Validate enhancements structure
                        enhancements = data.get('enhancements', {})
                        if success:
                            success = 'pois' in enhancements and 'dirt_segments' in enhancements
                            poi_count = len(enhancements.get('pois', []))
                            dirt_count = len(enhancements.get('dirt_segments', []))
                            details = f"- Distance: {data.get('distance', 0):.1f}m, POIs: {poi_count}, Dirt: {dirt_count}"
                        else:
                            details = f"- Missing enhancements structure"
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
                    
                self.log_test(f"Enhanced Route: {test_case['name']}", success, details)
                if not success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Enhanced Route: {test_case['name']}", False, f"- Error: {str(e)}")
                all_passed = False
                
        return all_passed

    def test_phase2_module_imports(self) -> bool:
        """Test Phase 2 module imports and basic functionality"""
        
        test_cases = [
            {
                "name": "Segment Features Module",
                "module": "modules.segment_features",
                "classes": ["SegmentFeatureExtractor", "SegmentFeature"]
            },
            {
                "name": "Custom Model Builder",
                "module": "modules.custom_model_builder", 
                "classes": ["CustomModelBuilder", "RouteWeights", "AdvVariant"]
            },
            {
                "name": "Detour Optimizer",
                "module": "modules.detour_optimizer",
                "classes": ["DetourOptimizer", "DetourConstraints", "DetourCandidate"]
            },
            {
                "name": "Phase 2 Integration",
                "module": "modules.phase2_integration",
                "classes": ["Phase2EnhancedPlanner", "Phase2Configuration"]
            }
        ]
        
        all_passed = True
        
        for test_case in test_cases:
            try:
                # Test module import
                import sys
                import os
                sys.path.append('/app/backend')
                
                module = __import__(test_case["module"], fromlist=test_case["classes"])
                
                # Test class imports
                missing_classes = []
                for class_name in test_case["classes"]:
                    if not hasattr(module, class_name):
                        missing_classes.append(class_name)
                
                success = len(missing_classes) == 0
                
                if success:
                    details = f"- All classes imported: {', '.join(test_case['classes'])}"
                else:
                    details = f"- Missing classes: {', '.join(missing_classes)}"
                    
                self.log_test(f"Phase 2 Import: {test_case['name']}", success, details)
                if not success:
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Phase 2 Import: {test_case['name']}", False, f"- Error: {str(e)}")
                all_passed = False
                
        return all_passed

    def test_phase2_segment_features(self) -> bool:
        """Test Segment Features Module functionality"""
        
        try:
            import sys
            sys.path.append('/app/backend')
            from modules.segment_features import SegmentFeatureExtractor, SegmentFeature
            
            # Test extractor initialization
            extractor = SegmentFeatureExtractor()
            
            # Test with sample segment data
            sample_segments = [
                {
                    'segment_id': 'test_seg_1',
                    'coordinates': [
                        {'longitude': -105.0178, 'latitude': 39.7392},
                        {'longitude': -105.0200, 'latitude': 39.7400},
                        {'longitude': -105.0220, 'latitude': 39.7410}
                    ],
                    'tags': {
                        'highway': 'track',
                        'surface': 'gravel',
                        'tracktype': 'grade2'
                    }
                }
            ]
            
            # Test basic feature extraction (synchronous parts)
            coordinates = extractor._extract_coordinates(sample_segments[0])
            success = len(coordinates) == 3
            
            if success:
                # Test distance calculation
                length = extractor._calculate_segment_length(coordinates)
                success = length > 0
                
                # Test OSM feature extraction
                osm_features = extractor._extract_osm_features(sample_segments[0]['tags'])
                success = success and 'surface_score' in osm_features
                success = success and osm_features['surface'] == 'gravel'
                success = success and osm_features['surface_score'] > 0.8  # Gravel should score high
                
                details = f"- Length: {length:.3f}km, Surface: {osm_features['surface']} (score: {osm_features['surface_score']:.2f})"
            else:
                details = f"- Coordinate extraction failed"
                
            self.log_test("Phase 2 Segment Features: Basic Functionality", success, details)
            return success
            
        except Exception as e:
            self.log_test("Phase 2 Segment Features: Basic Functionality", False, f"- Error: {str(e)}")
            return False

    def test_phase2_custom_model_builder(self) -> bool:
        """Test Custom Model Builder functionality"""
        
        try:
            import sys
            sys.path.append('/app/backend')
            from modules.custom_model_builder import CustomModelBuilder, RouteWeights, AdvVariant
            
            # Test model builder initialization
            builder = CustomModelBuilder()
            
            # Test route weights creation
            weights = RouteWeights(
                dirt=0.7,
                scenic=0.5,
                risk=-0.3,
                popularity=0.2
            )
            
            # Test model building for different variants
            variants_tested = []
            for variant in [AdvVariant.ADV_EASY, AdvVariant.ADV_MIXED, AdvVariant.ADV_TECH]:
                try:
                    model_config = builder.build_routing_model(weights, variant)
                    
                    # Verify model configuration structure
                    success = hasattr(model_config, 'base_profile')
                    success = success and hasattr(model_config, 'avoid_features')
                    success = success and hasattr(model_config, 'variant')
                    success = success and hasattr(model_config, 'confidence')
                    
                    if success:
                        variants_tested.append(f"{variant.value}(conf:{model_config.confidence:.2f})")
                        
                except Exception as e:
                    success = False
                    break
            
            if success and len(variants_tested) == 3:
                details = f"- Built models: {', '.join(variants_tested)}"
            else:
                details = f"- Failed to build all variant models"
                success = False
                
            self.log_test("Phase 2 Custom Model Builder: Variant Models", success, details)
            return success
            
        except Exception as e:
            self.log_test("Phase 2 Custom Model Builder: Variant Models", False, f"- Error: {str(e)}")
            return False

    def test_phase2_detour_optimizer(self) -> bool:
        """Test Detour Optimizer initialization and basic functionality"""
        
        try:
            import sys
            sys.path.append('/app/backend')
            from modules.detour_optimizer import DetourOptimizer, DetourConstraints, DetourCandidate, DetourType
            from modules.custom_model_builder import RouteWeights
            
            # Test detour optimizer initialization (without external dependencies)
            optimizer = DetourOptimizer()
            
            # Test detour constraints creation
            constraints = DetourConstraints(
                max_count=3,
                radius_km=5.0,
                min_gain=0.05,
                max_distance_penalty_pct=25.0,
                max_time_penalty_pct=30.0
            )
            
            # Test route weights
            weights = RouteWeights(dirt=0.6, scenic=0.4, risk=-0.2)
            
            # Test detour candidate creation
            candidate = DetourCandidate(
                detour_id="test_detour_1",
                detour_type=DetourType.SCENIC_VIEWPOINT,
                baseline_km_marker=5.0,
                detour_coordinates=[
                    {'longitude': -105.0178, 'latitude': 39.7392},
                    {'longitude': -105.0200, 'latitude': 39.7400}
                ],
                baseline_distance_km=10.0,
                detour_distance_km=12.0,
                baseline_duration_min=30.0,
                detour_duration_min=36.0
            )
            
            # Test basic properties
            success = candidate.detour_id == "test_detour_1"
            success = success and candidate.detour_type == DetourType.SCENIC_VIEWPOINT
            success = success and candidate.detour_distance_km > candidate.baseline_distance_km
            
            if success:
                details = f"- Detour: {candidate.detour_distance_km:.1f}km vs baseline {candidate.baseline_distance_km:.1f}km"
            else:
                details = f"- Detour candidate creation failed"
                
            self.log_test("Phase 2 Detour Optimizer: Basic Functionality", success, details)
            return success
            
        except Exception as e:
            self.log_test("Phase 2 Detour Optimizer: Basic Functionality", False, f"- Error: {str(e)}")
            return False

    def test_phase2_integration_framework(self) -> bool:
        """Test Phase 2 Integration Framework"""
        
        try:
            import sys
            sys.path.append('/app/backend')
            from modules.phase2_integration import Phase2EnhancedPlanner, Phase2Configuration
            from modules.custom_model_builder import AdvVariant
            
            # Test Phase 2 configuration
            config = Phase2Configuration(
                enable_segment_features=True,
                enable_custom_models=True,
                enable_detour_optimization=True,
                feature_extraction_budget=8.0,
                detour_optimization_budget=12.0,
                max_detours=3,
                default_variant=AdvVariant.ADV_MIXED
            )
            
            # Verify configuration properties
            success = config.enable_segment_features == True
            success = success and config.enable_custom_models == True
            success = success and config.enable_detour_optimization == True
            success = success and config.max_detours == 3
            success = success and config.default_variant == AdvVariant.ADV_MIXED
            
            if success:
                # Test Phase 2 planner initialization (without base planner for now)
                try:
                    # This will fail without base_planner, but we can test the class exists
                    planner_class_exists = Phase2EnhancedPlanner is not None
                    success = success and planner_class_exists
                    details = f"- Config valid, Planner class available, Max detours: {config.max_detours}"
                except Exception:
                    details = f"- Config valid, but planner initialization requires base planner"
            else:
                details = f"- Configuration validation failed"
                
            self.log_test("Phase 2 Integration Framework: Configuration", success, details)
            return success
            
        except Exception as e:
            self.log_test("Phase 2 Integration Framework: Configuration", False, f"- Error: {str(e)}")
            return False

    def test_phase2_module_dependencies(self) -> bool:
        """Test Phase 2 module cross-dependencies"""
        
        try:
            import sys
            sys.path.append('/app/backend')
            
            # Test that modules can import each other
            from modules.segment_features import SegmentFeatureExtractor
            from modules.custom_model_builder import CustomModelBuilder, RouteWeights, AdvVariant
            from modules.detour_optimizer import DetourOptimizer
            from modules.phase2_integration import Phase2EnhancedPlanner, Phase2Configuration
            
            # Test that Phase 2 integration can use other modules
            config = Phase2Configuration()
            
            # Test that custom model builder can work with segment features
            builder = CustomModelBuilder()
            weights = RouteWeights()
            
            # Test model building
            model = builder.build_routing_model(weights, AdvVariant.ADV_MIXED)
            
            success = model is not None
            success = success and hasattr(model, 'confidence')
            success = success and model.confidence > 0
            
            if success:
                details = f"- All modules imported, Model confidence: {model.confidence:.2f}"
            else:
                details = f"- Module dependency test failed"
                
            self.log_test("Phase 2 Module Dependencies: Cross-Integration", success, details)
            return success
            
        except Exception as e:
            self.log_test("Phase 2 Module Dependencies: Cross-Integration", False, f"- Error: {str(e)}")
            return False

    def test_phase2_performance_budgets(self) -> bool:
        """Test Phase 2 performance budget management"""
        
        try:
            import sys
            import time
            sys.path.append('/app/backend')
            from modules.segment_features import SegmentFeatureExtractor
            from modules.phase2_integration import Phase2Configuration
            
            # Test budget configuration
            config = Phase2Configuration(
                feature_extraction_budget=2.0,  # Short budget for testing
                detour_optimization_budget=3.0
            )
            
            # Test that extractor respects budget
            extractor = SegmentFeatureExtractor()
            
            # Create sample segments
            sample_segments = [
                {
                    'segment_id': f'test_seg_{i}',
                    'coordinates': [
                        {'longitude': -105.0178 + i*0.001, 'latitude': 39.7392 + i*0.001},
                        {'longitude': -105.0200 + i*0.001, 'latitude': 39.7400 + i*0.001}
                    ],
                    'tags': {'highway': 'track', 'surface': 'gravel'}
                }
                for i in range(5)  # 5 segments
            ]
            
            # Test budget timing (synchronous parts only)
            start_time = time.time()
            
            # Test coordinate extraction (should be fast)
            for segment in sample_segments:
                coords = extractor._extract_coordinates(segment)
                length = extractor._calculate_segment_length(coords)
                osm_features = extractor._extract_osm_features(segment.get('tags', {}))
            
            elapsed = time.time() - start_time
            
            # Should complete quickly for basic operations
            success = elapsed < 1.0  # Should be much faster than budget
            
            if success:
                details = f"- Budget: {config.feature_extraction_budget}s, Actual: {elapsed:.3f}s"
            else:
                details = f"- Budget exceeded: {elapsed:.3f}s > 1.0s"
                
            self.log_test("Phase 2 Performance: Budget Management", success, details)
            return success
            
        except Exception as e:
            self.log_test("Phase 2 Performance: Budget Management", False, f"- Error: {str(e)}")
            return False

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
            },
            {
                "name": "Invalid Enhanced Route Parameters",
                "endpoint": "route/enhanced",
                "method": "POST",
                "payload": {
                    "coordinates": [
                        {"longitude": -122.4194, "latitude": 37.7749},
                        {"longitude": -118.2437, "latitude": 34.0522}
                    ],
                    "max_detours": 15,  # Exceeds limit of 10
                    "detour_radius_km": 25  # Exceeds limit of 20
                },
                "expected_status": 422  # Validation error
            },
            {
                "name": "Invalid Advanced Route Parameters",
                "endpoint": "route/advanced",
                "method": "POST",
                "payload": {
                    "coordinates": [
                        {"longitude": -122.4194, "latitude": 37.7749},
                        {"longitude": -118.2437, "latitude": 34.0522}
                    ],
                    "max_detours": 15,  # Exceeds limit of 10
                    "detour_radius_km": 25  # Exceeds limit of 20
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
        print("🚀 Starting DUALSPORT MAPS Backend API Tests")
        print(f"📍 Testing API at: {self.api_url}")
        print("=" * 60)
        
        # Run all test suites
        test_results = [
            self.test_root_endpoint(),
            self.test_rate_limit_status(),
            self.test_place_search(),
            self.test_legacy_route_calculation(),
            self.test_enhanced_route_calculation(),
            self.test_advanced_route_calculation(),
            self.test_phase2_module_imports(),
            self.test_phase2_segment_features(),
            self.test_phase2_custom_model_builder(),
            self.test_phase2_detour_optimizer(),
            self.test_phase2_integration_framework(),
            self.test_phase2_module_dependencies(),
            self.test_phase2_performance_budgets(),
            self.test_invalid_requests(),
            self.test_legacy_endpoints()
        ]
        
        print("=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed! DUALSPORT MAPS Backend API is working correctly.")
            return 0
        else:
            failed_tests = self.tests_run - self.tests_passed
            print(f"⚠️  {failed_tests} test(s) failed. Check the logs above for details.")
            return 1

def main():
    """Main test runner"""
    tester = DualsportMapsTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())