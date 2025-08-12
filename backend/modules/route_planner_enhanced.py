"""
Enhanced route planner with robust fallbacks, detour handling, and confidence scoring.
Integrates all analysis modules for comprehensive ADV route planning.
"""

import asyncio
import logging
import math
import time
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import json

from .overpass_enhanced import OverpassEnhanced, OverpassWay
from .dem_analysis import DEMAnalysis, GradeSegment
from .imagery_validation import ImageryValidation, SegmentValidation
from .popularity_tracker import PopularityTracker, WayPopularity

logger = logging.getLogger(__name__)

@dataclass
class RouteOption:
    """Single route option with analysis data"""
    route_id: str
    name: str
    route_data: Dict[str, Any]  # GeoJSON or GPX data
    distance_m: float
    duration_s: float
    ascent_m: float
    descent_m: float
    off_pavement_pct: float
    surface_mix: Dict[str, float]
    road_class_mix: Dict[str, float]
    confidence: float  # 0-1 overall confidence
    flags: List[str]  # Analysis flags
    detours: List[Dict[str, Any]]  # Detour segments
    diagnostics: Dict[str, Any]  # Rich analysis data

@dataclass
class RoutePlanRequest:
    """Enhanced route planning request"""
    coordinates: List[Tuple[float, float]]  # [(lon, lat), ...]
    surface_preference: str = "mixed"
    technical_difficulty: str = "moderate"
    avoid_highways: bool = True
    avoid_primary: bool = False
    avoid_trunk: bool = True
    max_detours: int = 3
    detour_radius_km: float = 5.0
    trip_duration_hours: Optional[float] = None
    trip_distance_km: Optional[float] = None
    include_pois: bool = True
    include_dirt_segments: bool = True
    output_format: str = "geojson"

class EnhancedRoutePlanner:
    """Enhanced ADV route planner with comprehensive analysis"""
    
    def __init__(self, 
                 openroute_client,
                 overpass_endpoints: List[str] = None,
                 mapbox_token: str = None,
                 mapillary_token: str = None,
                 wikiloc_token: str = None,
                 feature_flags: Dict[str, bool] = None):
        
        self.openroute_client = openroute_client
        
        # Initialize analysis modules
        self.overpass = OverpassEnhanced(overpass_endpoints)
        self.dem_analysis = DEMAnalysis(mapbox_token)
        self.imagery_validation = ImageryValidation(mapillary_token)
        self.popularity_tracker = PopularityTracker(wikiloc_token)
        
        # Feature flags
        self.features = feature_flags or {
            'FEATURE_IMAGERY_VALIDATION': True,
            'FEATURE_POPULARITY_CONNECTORS': True,
            'FEATURE_DEM_ANALYSIS': bool(mapbox_token),
            'FEATURE_PARTNER_REVER': False,
            'FEATURE_DETOUR_LOOPS': True
        }
        
        # Time budgets (seconds)
        self.stage_budgets = {
            'overpass_discovery': 3.0,
            'dem_analysis': 3.0, 
            'imagery_validation': 2.0,
            'popularity_analysis': 2.0,
            'route_calculation': 4.0,
            'total_deadline': 12.0
        }
        
        # Analysis stats
        self.planning_stats = {
            "routes_planned": 0,
            "stage_timeouts": 0,
            "fallbacks_used": 0,
            "confidence_scores": [],
            "errors": 0
        }
    
    async def plan_enhanced_routes(self, request: RoutePlanRequest) -> Dict[str, Any]:
        """
        Plan enhanced ADV routes with comprehensive analysis
        
        Returns:
        {
            'route_options': List[RouteOption],
            'diagnostics': {
                'stage_timings': dict,
                'analysis_coverage': dict,
                'confidence_breakdown': dict,
                'flags_summary': List[str]
            },
            'stats': dict
        }
        """
        start_time = time.time()
        planning_deadline = start_time + self.stage_budgets['total_deadline']
        
        stage_timings = {}
        diagnostics = {
            'stage_timings': stage_timings,
            'analysis_coverage': {},
            'confidence_breakdown': {},
            'flags_summary': []
        }
        
        try:
            # Stage 1: Dirt discovery and anchor placement
            stage_start = time.time()
            dirt_discovery = await self._discover_dirt_corridor(
                request, min(self.stage_budgets['overpass_discovery'], 
                           planning_deadline - time.time())
            )
            stage_timings['overpass_discovery'] = time.time() - stage_start
            
            # Stage 2: Calculate base routes with anchors
            stage_start = time.time()
            base_routes = await self._calculate_base_routes(
                request, dirt_discovery,
                min(self.stage_budgets['route_calculation'],
                   planning_deadline - time.time())
            )
            stage_timings['route_calculation'] = time.time() - stage_start
            
            if not base_routes:
                return self._emergency_fallback_routes(request, diagnostics)
            
            # Stage 3: Enhanced analysis of route options
            enhanced_routes = []
            analysis_budget = max(0.5, planning_deadline - time.time())
            per_route_budget = analysis_budget / len(base_routes)
            
            for route_data in base_routes:
                if time.time() > planning_deadline:
                    logger.warning("Planning deadline exceeded, using basic routes")
                    break
                    
                enhanced_route = await self._enhance_route_analysis(
                    route_data, request, per_route_budget, diagnostics
                )
                enhanced_routes.append(enhanced_route)
            
            # Update diagnostics
            self._update_diagnostics(enhanced_routes, diagnostics)
            
            # Update stats
            elapsed = time.time() - start_time
            stats = {
                **self.planning_stats,
                "planning_time_seconds": elapsed,
                "routes_generated": len(enhanced_routes),
                "deadline_exceeded": elapsed > self.stage_budgets['total_deadline']
            }
            
            self.planning_stats["routes_planned"] += len(enhanced_routes)
            
            return {
                'route_options': enhanced_routes,
                'diagnostics': diagnostics,
                'stats': stats
            }
            
        except Exception as e:
            logger.error(f"Enhanced route planning failed: {e}")
            self.planning_stats["errors"] += 1
            
            # Emergency fallback
            return self._emergency_fallback_routes(request, diagnostics)
    
    async def _discover_dirt_corridor(self, 
                                    request: RoutePlanRequest, 
                                    budget: float) -> Dict[str, Any]:
        """Discover dirt roads and potential anchor points in corridor"""
        
        if budget <= 0 or not request.coordinates:
            return {'ways': [], 'anchor_vias': [], 'confidence': 0.0}
        
        try:
            # Extract start, vias, end from coordinates
            start_coord = request.coordinates[0]
            end_coord = request.coordinates[-1] 
            via_coords = request.coordinates[1:-1] if len(request.coordinates) > 2 else []
            
            discovery_result = await self.overpass.discover_dirt_corridor(
                start_coord, end_coord, via_coords, budget
            )
            
            return discovery_result
            
        except Exception as e:
            logger.error(f"Dirt discovery failed: {e}")
            return {'ways': [], 'anchor_vias': [], 'confidence': 0.0}
    
    async def _calculate_base_routes(self, 
                                   request: RoutePlanRequest, 
                                   dirt_discovery: Dict[str, Any],
                                   budget: float) -> List[Dict[str, Any]]:
        """Calculate base route options using dirt anchors"""
        
        if budget <= 0:
            return []
        
        base_coords = request.coordinates.copy()
        anchor_vias = dirt_discovery.get('anchor_vias', [])[:request.max_detours]
        
        routes = []
        route_variants = [
            ("ADV_Mixed", {"dirt_preference": 0.7, "scenic_bonus": 0.5}),
            ("ADV_Easy", {"dirt_preference": 0.4, "scenic_bonus": 0.3}),  
            ("Backroads_Bias", {"dirt_preference": 0.9, "scenic_bonus": 0.8})
        ]
        
        per_variant_budget = budget / len(route_variants)
        
        for variant_name, variant_params in route_variants:
            try:
                # Create coordinate list with strategic anchors
                route_coords = self._insert_anchor_vias(
                    base_coords, anchor_vias, variant_params
                )
                
                # Calculate route with OpenRouteService
                route_data = await self._calculate_single_route(
                    route_coords, request, variant_name, per_variant_budget
                )
                
                if route_data:
                    routes.append(route_data)
                    
            except Exception as e:
                logger.error(f"Failed to calculate {variant_name}: {e}")
                continue
        
        # Fallback: if no routes succeeded, try simple direct route
        if not routes:
            try:
                simple_route = await self._calculate_single_route(
                    base_coords, request, "Direct", budget * 0.3
                )
                if simple_route:
                    routes.append(simple_route)
                    self.planning_stats["fallbacks_used"] += 1
            except Exception as e:
                logger.error(f"Even simple route failed: {e}")
        
        return routes
    
    def _insert_anchor_vias(self, 
                          base_coords: List[Tuple[float, float]], 
                          anchor_vias: List[Tuple[float, float, str]],
                          variant_params: Dict[str, float]) -> List[Tuple[float, float]]:
        """Strategically insert anchor vias into route coordinates"""
        
        if not anchor_vias or len(base_coords) < 2:
            return base_coords
        
        # Filter anchors based on variant preferences
        dirt_pref = variant_params.get('dirt_preference', 0.5)
        scenic_pref = variant_params.get('scenic_bonus', 0.5)
        
        suitable_anchors = []
        for lon, lat, reason in anchor_vias:
            anchor_score = 0.0
            
            if 'dirt' in reason or 'gravel' in reason:
                anchor_score += dirt_pref * 0.6
            if 'scenic' in reason or 'viewpoint' in reason:
                anchor_score += scenic_pref * 0.4
                
            if anchor_score > 0.3:  # Threshold for inclusion
                suitable_anchors.append((lon, lat, reason, anchor_score))
        
        # Sort by score and take best ones
        suitable_anchors.sort(key=lambda x: x[3], reverse=True)
        top_anchors = suitable_anchors[:3]  # Max 3 anchors per route
        
        # Insert anchors at appropriate positions along route
        result_coords = [base_coords[0]]  # Start
        
        if len(base_coords) > 2:
            # Insert middle waypoints
            for coord in base_coords[1:-1]:
                result_coords.append(coord)
        
        # Insert anchors before end
        for lon, lat, reason, score in top_anchors:
            result_coords.append((lon, lat))
        
        result_coords.append(base_coords[-1])  # End
        
        return result_coords
    
    async def _calculate_single_route(self, 
                                    coordinates: List[Tuple[float, float]],
                                    request: RoutePlanRequest,
                                    route_name: str,
                                    budget: float) -> Optional[Dict[str, Any]]:
        """Calculate single route using OpenRouteService"""
        
        try:
            session = await self.openroute_client.get_session()
            
            # Build routing options based on request
            options = self._build_routing_options(request, route_name)
            
            payload = {
                "coordinates": coordinates,
                "format": "geojson",
                "instructions": True,
                "elevation": True,
                "extra_info": ["surface", "waytype", "steepness"],
                "options": options
            }
            
            # Make routing request
            url = f"{self.openroute_client.base_url}/v2/directions/cycling-regular/geojson"
            
            response = await session.post(
                url,
                headers=self.openroute_client.headers,
                json=payload,
                timeout=budget
            )
            
            if response.status_code == 200:
                route_data = response.json()
                
                return {
                    'route_id': f"{route_name.lower()}_{int(time.time())}",
                    'name': route_name,
                    'raw_data': route_data,
                    'coordinates': coordinates,
                    'options': options
                }
            else:
                logger.error(f"Routing failed for {route_name}: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Route calculation failed for {route_name}: {e}")
        
        return None
    
    def _build_routing_options(self, request: RoutePlanRequest, route_name: str) -> Dict[str, Any]:
        """Build OpenRouteService routing options based on request and route type"""
        
        options = {"avoid_features": []}
        
        # Base avoidance
        if request.avoid_highways:
            options["avoid_features"].append("highways")
        if request.avoid_trunk:
            # Note: "tollways" often includes major trunk roads in ORS
            pass  # Keep minimal for cycling profile
        
        # Route-specific customization would go here
        # This is simplified since cycling profile has limited options
        
        return options
    
    async def _enhance_route_analysis(self, 
                                    route_data: Dict[str, Any],
                                    request: RoutePlanRequest,
                                    budget: float,
                                    diagnostics: Dict[str, Any]) -> RouteOption:
        """Enhance route with comprehensive analysis"""
        
        route_coords = self._extract_route_coordinates(route_data)
        if not route_coords:
            return self._create_minimal_route_option(route_data)
        
        # Initialize analysis results
        analysis_results = {
            'dem': None,
            'imagery': None,
            'popularity': None
        }
        
        # Stage budgets for parallel analysis
        analysis_budgets = {
            'dem': budget * 0.4 if self.features['FEATURE_DEM_ANALYSIS'] else 0,
            'imagery': budget * 0.3 if self.features['FEATURE_IMAGERY_VALIDATION'] else 0,
            'popularity': budget * 0.3 if self.features['FEATURE_POPULARITY_CONNECTORS'] else 0
        }
        
        # Run analyses in parallel
        analysis_tasks = []
        
        if analysis_budgets['dem'] > 0:
            analysis_tasks.append(
                self._analyze_route_elevation(route_coords, analysis_budgets['dem'])
            )
        else:
            analysis_tasks.append(asyncio.create_task(self._empty_dem_analysis()))
        
        if analysis_budgets['imagery'] > 0:
            analysis_tasks.append(
                self._validate_route_imagery(route_coords, analysis_budgets['imagery'])
            )
        else:
            analysis_tasks.append(asyncio.create_task(self._empty_imagery_analysis()))
        
        if analysis_budgets['popularity'] > 0:
            analysis_tasks.append(
                self._analyze_route_popularity(route_coords, analysis_budgets['popularity'])
            )
        else:
            analysis_tasks.append(asyncio.create_task(self._empty_popularity_analysis()))
        
        try:
            # Wait for all analyses with timeout
            analysis_results['dem'], analysis_results['imagery'], analysis_results['popularity'] = \
                await asyncio.wait_for(asyncio.gather(*analysis_tasks), timeout=budget)
                
        except asyncio.TimeoutError:
            logger.warning(f"Route analysis timed out for {route_data['route_id']}")
            self.planning_stats["stage_timeouts"] += 1
        except Exception as e:
            logger.error(f"Route analysis failed: {e}")
        
        # Build enhanced route option
        return self._build_route_option(route_data, request, analysis_results)
    
    async def _analyze_route_elevation(self, 
                                     route_coords: List[Tuple[float, float]], 
                                     budget: float) -> Dict[str, Any]:
        """Analyze route elevation profile"""
        try:
            return await self.dem_analysis.analyze_route_grades(
                route_coords, budget_seconds=budget
            )
        except Exception as e:
            logger.error(f"DEM analysis failed: {e}")
            return await self._empty_dem_analysis()
    
    async def _validate_route_imagery(self, 
                                    route_coords: List[Tuple[float, float]], 
                                    budget: float) -> Dict[str, Any]:
        """Validate route using street-level imagery"""
        try:
            # Convert coordinates to segments for imagery validation
            segments = self._coords_to_segments(route_coords)
            return await self.imagery_validation.validate_segments(
                segments, budget_seconds=budget
            )
        except Exception as e:
            logger.error(f"Imagery validation failed: {e}")
            return await self._empty_imagery_analysis()
    
    async def _analyze_route_popularity(self, 
                                      route_coords: List[Tuple[float, float]], 
                                      budget: float) -> Dict[str, Any]:
        """Analyze route popularity from community data"""
        try:
            # Create bbox from route coordinates
            lons = [c[0] for c in route_coords]
            lats = [c[1] for c in route_coords]
            bbox = (min(lats), min(lons), max(lats), max(lons))
            
            # Convert coordinates to way-like structures
            route_ways = self._coords_to_ways(route_coords)
            
            return await self.popularity_tracker.analyze_route_popularity(
                route_ways, bbox, budget_seconds=budget
            )
        except Exception as e:
            logger.error(f"Popularity analysis failed: {e}")
            return await self._empty_popularity_analysis()
    
    def _extract_route_coordinates(self, route_data: Dict[str, Any]) -> List[Tuple[float, float]]:
        """Extract coordinate list from route data"""
        try:
            raw_data = route_data.get('raw_data', {})
            features = raw_data.get('features', [])
            
            if features and len(features) > 0:
                geometry = features[0].get('geometry', {})
                if geometry.get('type') == 'LineString':
                    coordinates = geometry.get('coordinates', [])
                    return [(coord[0], coord[1]) for coord in coordinates]  # (lon, lat)
        except Exception as e:
            logger.error(f"Failed to extract route coordinates: {e}")
        
        return []
    
    def _coords_to_segments(self, route_coords: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
        """Convert route coordinates to segments for analysis"""
        segments = []
        
        if len(route_coords) < 2:
            return segments
        
        # Sample every ~1km for analysis
        sample_interval = max(1, len(route_coords) // 20)  # ~20 segments max
        
        for i in range(0, len(route_coords) - sample_interval, sample_interval):
            segment_coords = route_coords[i:i + sample_interval + 1]
            
            segment = {
                'segment_id': f"seg_{i}",
                'coordinates': [
                    {'longitude': coord[0], 'latitude': coord[1]} 
                    for coord in segment_coords
                ],
                'tags': {}  # Would be populated from OSM data if available
            }
            segments.append(segment)
        
        return segments
    
    def _coords_to_ways(self, route_coords: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
        """Convert route coordinates to way-like structures for popularity analysis"""
        ways = []
        
        if len(route_coords) < 2:
            return ways
        
        # Create single way from all coordinates
        way = {
            'way_id': f"route_way_{hash(str(route_coords)) % 100000}",
            'coordinates': [
                {'longitude': coord[0], 'latitude': coord[1]} 
                for coord in route_coords
            ],
            'tags': {}
        }
        ways.append(way)
        
        return ways
    
    def _build_route_option(self, 
                          route_data: Dict[str, Any],
                          request: RoutePlanRequest,
                          analysis_results: Dict[str, Any]) -> RouteOption:
        """Build comprehensive route option from analysis results"""
        
        raw_data = route_data.get('raw_data', {})
        features = raw_data.get('features', [])
        properties = features[0].get('properties', {}) if features else {}
        
        # Extract basic route metrics
        summary = properties.get('summary', {})
        distance_m = summary.get('distance', 0)
        duration_s = summary.get('duration', 0)
        
        # Extract elevation data
        dem_data = analysis_results.get('dem', {})
        dem_summary = dem_data.get('summary', {})
        ascent_m = dem_summary.get('total_ascent_m', 0)
        descent_m = dem_summary.get('total_descent_m', 0)
        
        # Calculate surface mix (simplified)
        surface_mix = self._calculate_surface_mix(properties, analysis_results)
        off_pavement_pct = surface_mix.get('gravel', 0) + surface_mix.get('dirt', 0)
        
        # Calculate road class mix (simplified)
        road_class_mix = self._calculate_road_class_mix(properties)
        
        # Calculate confidence score
        confidence = self._calculate_route_confidence(analysis_results, properties)
        
        # Generate flags
        flags = self._generate_route_flags(analysis_results, dem_summary)
        
        # Generate detours (placeholder)
        detours = self._generate_detour_info(route_data, analysis_results)
        
        # Build diagnostics
        diagnostics = self._build_route_diagnostics(analysis_results, properties)
        
        return RouteOption(
            route_id=route_data['route_id'],
            name=route_data['name'],
            route_data=raw_data,
            distance_m=distance_m,
            duration_s=duration_s,
            ascent_m=ascent_m,
            descent_m=descent_m,
            off_pavement_pct=off_pavement_pct,
            surface_mix=surface_mix,
            road_class_mix=road_class_mix,
            confidence=confidence,
            flags=flags,
            detours=detours,
            diagnostics=diagnostics
        )
    
    def _calculate_surface_mix(self, 
                             route_properties: Dict[str, Any], 
                             analysis_results: Dict[str, Any]) -> Dict[str, float]:
        """Calculate surface type percentages"""
        
        # Default surface mix
        surface_mix = {
            "asphalt": 0.5,
            "gravel": 0.3,
            "dirt": 0.2
        }
        
        # TODO: Parse actual surface data from route properties and analysis
        # This would involve processing the 'extras' -> 'surface' data from ORS
        
        return surface_mix
    
    def _calculate_road_class_mix(self, route_properties: Dict[str, Any]) -> Dict[str, float]:
        """Calculate road class percentages"""
        
        # Default road class mix for ADV routes
        road_class_mix = {
            "track": 0.4,
            "unclassified": 0.3,
            "tertiary": 0.2,
            "secondary": 0.1
        }
        
        # TODO: Parse actual waytype data from route properties
        
        return road_class_mix
    
    def _calculate_route_confidence(self, 
                                  analysis_results: Dict[str, Any], 
                                  route_properties: Dict[str, Any]) -> float:
        """Calculate overall confidence score for route (0-1)"""
        
        confidence = 0.5  # Base confidence
        
        # DEM analysis contribution
        dem_data = analysis_results.get('dem', {})
        if dem_data and dem_data.get('elevation_profile'):
            confidence += 0.15  # Bonus for elevation data
            
        dem_summary = dem_data.get('summary', {})
        if dem_summary.get('flags') and 'no_elevation_data' not in dem_summary.get('flags', []):
            confidence += 0.1
        
        # Imagery validation contribution
        imagery_data = analysis_results.get('imagery', {})
        imagery_summary = imagery_data.get('summary', {})
        if imagery_summary.get('confidence_score', 0) > 0.5:
            confidence += 0.1
        if imagery_summary.get('total_frames', 0) > 0:
            confidence += 0.05
        
        # Popularity contribution
        popularity_data = analysis_results.get('popularity', {})
        popularity_summary = popularity_data.get('summary', {})
        if popularity_summary.get('avg_popularity', 0) > 0.3:
            confidence += 0.1
        if popularity_summary.get('motorcycle_traces', 0) > 0:
            confidence += 0.1
        
        # Route completeness bonus
        summary = route_properties.get('summary', {})
        if summary.get('distance', 0) > 0 and summary.get('duration', 0) > 0:
            confidence += 0.1
        
        return max(0.0, min(1.0, confidence))
    
    def _generate_route_flags(self, 
                            analysis_results: Dict[str, Any], 
                            dem_summary: Dict[str, Any]) -> List[str]:
        """Generate warning and info flags for route"""
        
        flags = []
        
        # DEM-based flags
        dem_flags = dem_summary.get('flags', [])
        if 'super_steep' in dem_flags:
            flags.append('challenging_grades')
        if 'washout_risk' in dem_flags:
            flags.append('washout_potential')
        if 'scenic_elevation' in dem_flags:
            flags.append('scenic_views')
        
        # Imagery validation flags
        imagery_data = analysis_results.get('imagery', {})
        imagery_summary = imagery_data.get('summary', {})
        imagery_flags = imagery_summary.get('flags', [])
        
        if 'verified_unpaved' in imagery_flags:
            flags.append('confirmed_dirt')
        if 'possible_gate' in imagery_flags:
            flags.append('access_check_needed')
        if 'recent_imagery' in imagery_flags:
            flags.append('recently_validated')
        
        # Popularity flags
        popularity_data = analysis_results.get('popularity', {})
        popularity_summary = popularity_data.get('summary', {})
        
        if popularity_summary.get('motorcycle_traces', 0) > 5:
            flags.append('popular_with_riders')
        elif popularity_summary.get('total_traces', 0) == 0:
            flags.append('uncharted_territory')
        
        return flags
    
    def _generate_detour_info(self, 
                            route_data: Dict[str, Any], 
                            analysis_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate detour segment information"""
        
        detours = []
        
        # This would identify specific detour segments with labels
        # For now, return empty list
        
        return detours
    
    def _build_route_diagnostics(self, 
                               analysis_results: Dict[str, Any], 
                               route_properties: Dict[str, Any]) -> Dict[str, Any]:
        """Build comprehensive diagnostics for route"""
        
        diagnostics = {
            'dem_analysis': analysis_results.get('dem', {}),
            'imagery_validation': analysis_results.get('imagery', {}),
            'popularity_analysis': analysis_results.get('popularity', {}),
            'route_properties': route_properties
        }
        
        return diagnostics
    
    def _create_minimal_route_option(self, route_data: Dict[str, Any]) -> RouteOption:
        """Create minimal route option when analysis fails"""
        
        return RouteOption(
            route_id=route_data.get('route_id', 'minimal'),
            name=route_data.get('name', 'Basic Route'),
            route_data=route_data.get('raw_data', {}),
            distance_m=0,
            duration_s=0,
            ascent_m=0,
            descent_m=0,
            off_pavement_pct=0.0,
            surface_mix={'unknown': 1.0},
            road_class_mix={'unknown': 1.0},
            confidence=0.1,
            flags=['minimal_analysis'],
            detours=[],
            diagnostics={'error': 'Analysis failed'}
        )
    
    async def _empty_dem_analysis(self) -> Dict[str, Any]:
        """Return empty DEM analysis when disabled or failed"""
        return {
            'elevation_profile': [],
            'grade_segments': [],
            'summary': {
                'total_ascent_m': 0.0,
                'total_descent_m': 0.0,
                'max_grade_pct': 0.0,
                'avg_grade_pct': 0.0,
                'ridge_score': 0.0,
                'flags': ['no_elevation_data']
            },
            'stats': {}
        }
    
    async def _empty_imagery_analysis(self) -> Dict[str, Any]:
        """Return empty imagery analysis when disabled or failed"""
        return {
            'segment_validations': [],
            'summary': {
                'total_frames': 0,
                'verified_segments': 0,
                'confidence_score': 0.0,
                'flags': ['no_imagery_data']
            },
            'stats': {}
        }
    
    async def _empty_popularity_analysis(self) -> Dict[str, Any]:
        """Return empty popularity analysis when disabled or failed"""
        return {
            'way_popularity': {},
            'summary': {
                'avg_popularity': 0.0,
                'total_traces': 0,
                'motorcycle_traces': 0,
                'coverage_pct': 0.0
            },
            'stats': {}
        }
    
    def _emergency_fallback_routes(self, 
                                 request: RoutePlanRequest, 
                                 diagnostics: Dict[str, Any]) -> Dict[str, Any]:
        """Generate emergency fallback when all else fails"""
        
        # Create minimal direct route
        fallback_route = RouteOption(
            route_id='fallback_direct',
            name='Direct Route (Fallback)',
            route_data={
                'type': 'FeatureCollection',
                'features': [{
                    'type': 'Feature',
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': request.coordinates
                    },
                    'properties': {
                        'summary': {'distance': 0, 'duration': 0}
                    }
                }]
            },
            distance_m=0,
            duration_s=0,
            ascent_m=0,
            descent_m=0,
            off_pavement_pct=0.0,
            surface_mix={'unknown': 1.0},
            road_class_mix={'unknown': 1.0},
            confidence=0.1,
            flags=['emergency_fallback', 'no_analysis'],
            detours=[],
            diagnostics={'fallback_reason': 'All route planning stages failed'}
        )
        
        diagnostics['flags_summary'] = ['emergency_fallback_used']
        
        self.planning_stats["fallbacks_used"] += 1
        
        return {
            'route_options': [fallback_route],
            'diagnostics': diagnostics,
            'stats': {
                **self.planning_stats,
                "planning_time_seconds": 0.0,
                "routes_generated": 1,
                "emergency_fallback": True
            }
        }
    
    def _update_diagnostics(self, 
                          routes: List[RouteOption], 
                          diagnostics: Dict[str, Any]):
        """Update diagnostics with route analysis results"""
        
        if not routes:
            return
        
        # Analysis coverage
        dem_coverage = sum(1 for r in routes if r.diagnostics.get('dem_analysis', {}).get('elevation_profile'))
        imagery_coverage = sum(1 for r in routes if r.diagnostics.get('imagery_validation', {}).get('segment_validations'))
        popularity_coverage = sum(1 for r in routes if r.diagnostics.get('popularity_analysis', {}).get('way_popularity'))
        
        diagnostics['analysis_coverage'] = {
            'dem_analysis_pct': (dem_coverage / len(routes)) * 100,
            'imagery_validation_pct': (imagery_coverage / len(routes)) * 100,
            'popularity_analysis_pct': (popularity_coverage / len(routes)) * 100
        }
        
        # Confidence breakdown
        confidences = [r.confidence for r in routes]
        diagnostics['confidence_breakdown'] = {
            'avg_confidence': sum(confidences) / len(confidences),
            'min_confidence': min(confidences),
            'max_confidence': max(confidences)
        }
        
        # Collect all flags
        all_flags = set()
        for route in routes:
            all_flags.update(route.flags)
        
        diagnostics['flags_summary'] = sorted(list(all_flags))