"""
Detour Optimizer Module - Phase 2
Smart detour selection system for ADV route enhancement.

Along a baseline route, samples every N km and tries up to K dirt detours 
within radius R. Accepts detours that increase off-pavement/scenic score 
within time/distance budget constraints.
"""

import asyncio
import logging
import math
import time
from typing import List, Dict, Any, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum
import json
import numpy as np

from .segment_features import SegmentFeature
from .custom_model_builder import ModelConfiguration, RouteWeights

logger = logging.getLogger(__name__)

class DetourType(Enum):
    """Types of detours the optimizer can find"""
    DIRT_SEGMENT = "dirt_segment"
    SCENIC_LOOP = "scenic_loop"
    POI_VISIT = "poi_visit"
    TECHNICAL_CHALLENGE = "technical_challenge"

@dataclass
class DetourCandidate:
    """A potential detour segment or loop"""
    detour_id: str
    detour_type: DetourType
    start_point: Tuple[float, float]  # (lon, lat) where detour begins
    end_point: Tuple[float, float]    # (lon, lat) where detour rejoins
    detour_coordinates: List[Tuple[float, float]]  # Full detour path
    
    # Metrics
    detour_distance_km: float
    detour_duration_min: float
    baseline_distance_km: float  # Original direct distance
    baseline_duration_min: float # Original direct time
    
    # Scores
    dirt_gain: float             # Improvement in dirt score (0-1)
    scenic_gain: float           # Improvement in scenic score (0-1) 
    popularity_gain: float       # Improvement in popularity (0-1)
    risk_penalty: float          # Risk penalty incurred (0-1)
    
    # Overall evaluation
    objective_gain: float        # Weighted objective improvement
    efficiency_ratio: float      # Gain per km added
    confidence: float            # Confidence in detour quality (0-1)
    
    # Context
    baseline_km_marker: float    # Where on baseline route this detour applies
    segment_features: List[SegmentFeature]  # Features of detour segments

@dataclass
class DetourConstraints:
    """Constraints for detour optimization"""
    max_count: int = 3               # Maximum number of detours
    radius_km: float = 5.0           # Maximum detour radius
    sample_km: float = 5.0           # Sample baseline every N km for detours
    min_gain: float = 0.05           # Minimum objective gain to accept detour
    max_time_penalty_pct: float = 50.0  # Max % time increase per detour
    max_distance_penalty_pct: float = 30.0  # Max % distance increase per detour
    max_total_time_penalty_pct: float = 100.0  # Max total time increase
    
@dataclass
class DetourOptimizationResult:
    """Result of detour optimization process"""
    accepted_detours: List[DetourCandidate]
    rejected_detours: List[DetourCandidate]
    baseline_route: Dict[str, Any]
    enhanced_route: Dict[str, Any]
    
    # Summary metrics
    total_dirt_gain: float
    total_scenic_gain: float
    total_risk_penalty: float
    total_distance_added_km: float
    total_time_added_min: float
    
    # Diagnostics
    sampling_points: int
    candidates_evaluated: int
    optimization_time_s: float
    constraints_applied: DetourConstraints
    
class DetourOptimizer:
    """Optimize routes by finding and inserting valuable detours"""
    
    def __init__(self,
                 segment_extractor=None,
                 route_planner=None,
                 overpass_client=None):
        self.segment_extractor = segment_extractor
        self.route_planner = route_planner
        self.overpass_client = overpass_client
        
        # Optimization parameters
        self.candidate_search_radius_multiplier = 1.5  # Search wider than constraint radius
        self.min_detour_length_m = 500  # Minimum detour length to consider
        self.max_detour_length_km = 20.0  # Maximum single detour length
        self.parallel_evaluation_batch = 5  # Evaluate up to 5 detours in parallel
        
        # Scoring weights for detour evaluation
        self.evaluation_weights = {
            'dirt_gain': 0.4,
            'scenic_gain': 0.3,
            'popularity_gain': 0.2,
            'risk_penalty': -0.3,
            'efficiency_bonus': 0.2
        }
        
        self.optimization_stats = {
            "routes_optimized": 0,
            "detours_found": 0,
            "detours_accepted": 0,
            "detours_rejected": 0,
            "sampling_points_processed": 0,
            "candidate_evaluations": 0,
            "errors": 0
        }

    async def optimize_route_with_detours(self,
                                        baseline_route: Dict[str, Any],
                                        route_weights: RouteWeights,
                                        constraints: DetourConstraints,
                                        budget_seconds: float = 15.0) -> DetourOptimizationResult:
        """
        Optimize a baseline route by finding and adding valuable detours
        
        Args:
            baseline_route: Base route to enhance with detours
            route_weights: User routing preferences
            constraints: Detour constraints and limits
            budget_seconds: Time budget for optimization
            
        Returns:
            DetourOptimizationResult with enhanced route and diagnostics
        """
        
        start_time = time.time()
        
        logger.info(f"Optimizing route with detours: {constraints.max_count} max, {constraints.radius_km}km radius")
        
        try:
            # Extract baseline route coordinates
            baseline_coords = self._extract_route_coordinates(baseline_route)
            if len(baseline_coords) < 2:
                return self._create_no_detours_result(baseline_route, constraints, 0.0)
            
            # Sample points along baseline for detour search
            sampling_points = self._sample_baseline_points(baseline_coords, constraints.sample_km)
            self.optimization_stats["sampling_points_processed"] += len(sampling_points)
            
            logger.info(f"Sampling {len(sampling_points)} points for detour search")
            
            # Find detour candidates at each sampling point
            all_candidates = []
            candidates_budget = budget_seconds * 0.6  # 60% for candidate discovery
            per_point_budget = candidates_budget / len(sampling_points) if sampling_points else 0
            
            for i, point in enumerate(sampling_points):
                if time.time() - start_time > budget_seconds * 0.8:
                    logger.warning(f"Optimization budget nearly exhausted, processed {i}/{len(sampling_points)} points")
                    break
                
                point_candidates = await self._find_detour_candidates_at_point(
                    point, baseline_coords, constraints, per_point_budget
                )
                all_candidates.extend(point_candidates)
            
            logger.info(f"Found {len(all_candidates)} total detour candidates")
            
            # Evaluate and rank candidates
            evaluation_budget = budget_seconds * 0.3  # 30% for evaluation
            evaluated_candidates = await self._evaluate_detour_candidates(
                all_candidates, route_weights, evaluation_budget
            )
            
            # Select optimal set of detours
            selection_budget = budget_seconds * 0.1  # 10% for selection
            selected_detours = await self._select_optimal_detours(
                evaluated_candidates, constraints, selection_budget
            )
            
            # Build enhanced route with selected detours
            enhanced_route = await self._build_enhanced_route(
                baseline_route, selected_detours
            )
            
            # Create result with full diagnostics
            optimization_time = time.time() - start_time
            result = self._create_optimization_result(
                baseline_route, enhanced_route, selected_detours, 
                evaluated_candidates, optimization_time, constraints, sampling_points
            )
            
            self.optimization_stats["routes_optimized"] += 1
            self.optimization_stats["detours_accepted"] += len(selected_detours)
            self.optimization_stats["detours_rejected"] += len(evaluated_candidates) - len(selected_detours)
            
            logger.info(f"Route optimization completed: {len(selected_detours)} detours in {optimization_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Route optimization failed: {e}")
            self.optimization_stats["errors"] += 1
            return self._create_no_detours_result(baseline_route, constraints, time.time() - start_time)

    def _extract_route_coordinates(self, route: Dict[str, Any]) -> List[Tuple[float, float]]:
        """Extract coordinate list from route data"""
        
        coordinates = []
        
        # Try different route formats
        if 'geometry' in route:
            geometry = route['geometry']
            if isinstance(geometry, dict) and 'coordinates' in geometry:
                coords = geometry['coordinates']
                if geometry.get('type') == 'LineString':
                    coordinates = [(c[0], c[1]) for c in coords]
                elif geometry.get('type') == 'MultiLineString':
                    # Flatten MultiLineString
                    for line in coords:
                        coordinates.extend([(c[0], c[1]) for c in line])
        
        elif 'coordinates' in route:
            coords_data = route['coordinates']
            if isinstance(coords_data, list):
                for coord in coords_data[:1000]:  # Limit for performance
                    if isinstance(coord, dict):
                        lon = coord.get('longitude', coord.get('lon', 0))
                        lat = coord.get('latitude', coord.get('lat', 0))
                        coordinates.append((lon, lat))
                    elif isinstance(coord, (list, tuple)) and len(coord) >= 2:
                        coordinates.append((coord[0], coord[1]))
        
        return coordinates

    def _sample_baseline_points(self,
                              baseline_coords: List[Tuple[float, float]],
                              sample_km: float) -> List[Dict[str, Any]]:
        """Sample points along baseline route for detour search"""
        
        if len(baseline_coords) < 2:
            return []
        
        sampling_points = []
        total_distance = 0.0
        last_sample_distance = 0.0
        
        for i in range(len(baseline_coords) - 1):
            lon1, lat1 = baseline_coords[i]
            lon2, lat2 = baseline_coords[i + 1]
            
            segment_distance = self._haversine_km(lat1, lon1, lat2, lon2)
            total_distance += segment_distance
            
            # Add sampling points at regular intervals
            while total_distance - last_sample_distance >= sample_km:
                # Calculate position along segment
                sample_distance = last_sample_distance + sample_km
                distance_into_segment = sample_distance - (total_distance - segment_distance)
                
                if segment_distance > 0:
                    ratio = distance_into_segment / segment_distance
                    sample_lon = lon1 + (lon2 - lon1) * ratio
                    sample_lat = lat1 + (lat2 - lat1) * ratio
                    
                    sampling_point = {
                        'coordinates': (sample_lon, sample_lat),
                        'baseline_km': sample_distance,
                        'segment_index': i,
                        'upstream_coords': baseline_coords[max(0, i-2):i+1],
                        'downstream_coords': baseline_coords[i+1:min(len(baseline_coords), i+4)]
                    }
                    
                    sampling_points.append(sampling_point)
                    last_sample_distance = sample_distance
        
        return sampling_points

    async def _find_detour_candidates_at_point(self,
                                             sampling_point: Dict[str, Any],
                                             baseline_coords: List[Tuple[float, float]],
                                             constraints: DetourConstraints,
                                             budget: float) -> List[DetourCandidate]:
        """Find detour candidates at a specific sampling point"""
        
        point_coords = sampling_point['coordinates']
        baseline_km = sampling_point['baseline_km']
        
        candidates = []
        
        try:
            # Search for interesting ways/paths near this point
            if self.overpass_client:
                search_radius = constraints.radius_km * self.candidate_search_radius_multiplier
                nearby_ways = await self._search_nearby_ways(
                    point_coords, search_radius, budget * 0.7
                )
                
                # Convert ways to detour candidates
                for way in nearby_ways[:10]:  # Limit candidates per point
                    candidate = await self._way_to_detour_candidate(
                        way, sampling_point, baseline_coords, constraints
                    )
                    if candidate:
                        candidates.append(candidate)
            
            # Generate loop detours (out and back)
            loop_candidates = await self._generate_loop_detours(
                sampling_point, constraints, budget * 0.3
            )
            candidates.extend(loop_candidates)
            
        except Exception as e:
            logger.error(f"Detour candidate search failed at point {point_coords}: {e}")
        
        return candidates

    async def _search_nearby_ways(self,
                                center: Tuple[float, float],
                                radius_km: float,
                                budget: float) -> List[Dict[str, Any]]:
        """Search for interesting ways near a point using Overpass"""
        
        if not self.overpass_client:
            return []
        
        lon, lat = center
        
        # Build Overpass query for interesting ADV ways
        query = f"""
        [out:json][timeout:{int(budget)}];
        (
          way["highway"~"^(track|path|unclassified|tertiary)$"]
             ["surface"~"^(gravel|dirt|compacted|ground|unpaved)$"]
             (around:{radius_km * 1000},{lat},{lon});
          way["highway"="track"]
             ["tracktype"~"^(grade1|grade2|grade3)$"]
             (around:{radius_km * 1000},{lat},{lon});
        );
        out geom;
        """
        
        try:
            result = await self.overpass_client.execute_query_with_timeout(query, budget)
            ways = result.get('elements', [])
            
            # Filter and score ways
            scored_ways = []
            for way in ways:
                if self._is_suitable_detour_way(way):
                    score = self._score_way_for_detour(way)
                    way['detour_score'] = score
                    scored_ways.append(way)
            
            # Return top scoring ways
            scored_ways.sort(key=lambda w: w['detour_score'], reverse=True)
            return scored_ways[:20]  # Top 20 ways
            
        except Exception as e:
            logger.error(f"Overpass search failed: {e}")
            return []

    def _is_suitable_detour_way(self, way: Dict[str, Any]) -> bool:
        """Check if a way is suitable for detour consideration"""
        
        tags = way.get('tags', {})
        
        # Must have coordinates
        if not way.get('geometry'):
            return False
        
        # Check length constraints
        coords = [(node['lon'], node['lat']) for node in way['geometry']]
        length_km = sum(
            self._haversine_km(coords[i][1], coords[i][0], coords[i+1][1], coords[i+1][0])
            for i in range(len(coords) - 1)
        )
        
        if length_km < (self.min_detour_length_m / 1000) or length_km > self.max_detour_length_km:
            return False
        
        # Must be accessible to motorcycles
        access = tags.get('access', '')
        motor_vehicle = tags.get('motor_vehicle', '')
        motorcycle = tags.get('motorcycle', '')
        
        if access == 'no' or motor_vehicle == 'no':
            return False
        if motorcycle == 'no':
            return False
        
        return True

    def _score_way_for_detour(self, way: Dict[str, Any]) -> float:
        """Score a way for detour attractiveness (0-1)"""
        
        tags = way.get('tags', {})
        score = 0.5  # Base score
        
        # Surface scoring
        surface = tags.get('surface', '').lower()
        surface_scores = {
            'gravel': 0.9, 'compacted': 0.8, 'dirt': 0.7,
            'ground': 0.6, 'unpaved': 0.5
        }
        score += surface_scores.get(surface, 0.0) * 0.3
        
        # Track type scoring
        tracktype = tags.get('tracktype', '').lower()
        tracktype_scores = {
            'grade1': 0.8, 'grade2': 0.9, 'grade3': 0.7, 'grade4': 0.4
        }
        score += tracktype_scores.get(tracktype, 0.0) * 0.2
        
        # Highway type scoring  
        highway = tags.get('highway', '').lower()
        highway_scores = {
            'track': 0.9, 'path': 0.6, 'unclassified': 0.5, 'tertiary': 0.4
        }
        score += highway_scores.get(highway, 0.0) * 0.2
        
        # Bonus for scenic indicators
        name = tags.get('name', '').lower()
        if any(word in name for word in ['scenic', 'view', 'ridge', 'mountain', 'forest']):
            score += 0.1
        
        return min(1.0, score)

    async def _way_to_detour_candidate(self,
                                     way: Dict[str, Any],
                                     sampling_point: Dict[str, Any],
                                     baseline_coords: List[Tuple[float, float]],
                                     constraints: DetourConstraints) -> Optional[DetourCandidate]:
        """Convert an OSM way to a detour candidate"""
        
        try:
            way_coords = [(node['lon'], node['lat']) for node in way['geometry']]
            
            if len(way_coords) < 2:
                return None
            
            # Find best connection points to baseline
            sampling_coords = sampling_point['coordinates']
            
            # Find closest points on way to sampling point
            start_point, start_idx = self._find_closest_point_on_line(sampling_coords, way_coords)
            
            # Determine detour type based on way characteristics
            tags = way.get('tags', {})
            detour_type = self._classify_detour_type(tags)
            
            # Calculate detour metrics
            detour_distance = sum(
                self._haversine_km(way_coords[i][1], way_coords[i][0], way_coords[i+1][1], way_coords[i+1][0])
                for i in range(len(way_coords) - 1)
            )
            
            # Create candidate
            candidate = DetourCandidate(
                detour_id=f"way_{way.get('id', hash(str(way)))}",
                detour_type=detour_type,
                start_point=start_point,
                end_point=way_coords[-1],  # End of way
                detour_coordinates=way_coords,
                detour_distance_km=detour_distance,
                detour_duration_min=detour_distance * 4,  # Estimate 15 km/h average
                baseline_distance_km=0.1,  # Minimal baseline bypass
                baseline_duration_min=0.1 * 2,  # Estimate 30 km/h baseline
                dirt_gain=way.get('detour_score', 0.5),  # Use way score as dirt potential
                scenic_gain=0.3,  # Default scenic gain
                popularity_gain=0.0,  # Will be updated during evaluation
                risk_penalty=0.1,  # Default low risk
                objective_gain=0.0,  # Will be calculated
                efficiency_ratio=0.0,  # Will be calculated
                confidence=0.6,  # Medium confidence
                baseline_km_marker=sampling_point['baseline_km'],
                segment_features=[]  # Will be populated during evaluation
            )
            
            return candidate
            
        except Exception as e:
            logger.error(f"Way to detour conversion failed: {e}")
            return None

    def _classify_detour_type(self, tags: Dict[str, str]) -> DetourType:
        """Classify detour type based on OSM tags"""
        
        highway = tags.get('highway', '').lower()
        surface = tags.get('surface', '').lower()
        name = tags.get('name', '').lower()
        
        # Technical challenge indicators
        if any(word in name for word in ['technical', 'difficult', 'expert']):
            return DetourType.TECHNICAL_CHALLENGE
        
        # Scenic loop indicators
        if any(word in name for word in ['scenic', 'view', 'loop', 'circuit']):
            return DetourType.SCENIC_LOOP
        
        # Dirt segment (most common)
        if surface in ['gravel', 'dirt', 'compacted', 'ground']:
            return DetourType.DIRT_SEGMENT
        
        return DetourType.DIRT_SEGMENT  # Default

    async def _generate_loop_detours(self,
                                   sampling_point: Dict[str, Any],
                                   constraints: DetourConstraints,
                                   budget: float) -> List[DetourCandidate]:
        """Generate synthetic loop detours from sampling point"""
        
        # For now, return empty list
        # In full implementation, this would generate geometric loops
        # at various distances and directions from the sampling point
        
        return []

    async def _evaluate_detour_candidates(self,
                                        candidates: List[DetourCandidate],
                                        route_weights: RouteWeights,
                                        budget: float) -> List[DetourCandidate]:
        """Evaluate and score all detour candidates"""
        
        if not candidates:
            return []
        
        logger.info(f"Evaluating {len(candidates)} detour candidates")
        
        # Process in batches for efficiency
        evaluated = []
        batch_size = self.parallel_evaluation_batch
        per_candidate_budget = budget / len(candidates) if candidates else 0
        
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            
            # Evaluate batch in parallel
            evaluation_tasks = [
                self._evaluate_single_candidate(candidate, route_weights, per_candidate_budget)
                for candidate in batch
            ]
            
            try:
                batch_results = await asyncio.gather(*evaluation_tasks, return_exceptions=True)
                
                for result in batch_results:
                    if isinstance(result, DetourCandidate):
                        evaluated.append(result)
                        self.optimization_stats["candidate_evaluations"] += 1
                    elif isinstance(result, Exception):
                        logger.error(f"Candidate evaluation failed: {result}")
                        
            except Exception as e:
                logger.error(f"Batch evaluation failed: {e}")
        
        # Sort by objective gain
        evaluated.sort(key=lambda c: c.objective_gain, reverse=True)
        
        logger.info(f"Evaluated {len(evaluated)} candidates successfully")
        return evaluated

    async def _evaluate_single_candidate(self,
                                       candidate: DetourCandidate,
                                       route_weights: RouteWeights,
                                       budget: float) -> DetourCandidate:
        """Evaluate a single detour candidate"""
        
        try:
            # Get segment features for detour if extractor available
            if self.segment_extractor:
                # Convert detour to segment format
                detour_segment = {
                    'segment_id': candidate.detour_id,
                    'coordinates': [
                        {'longitude': c[0], 'latitude': c[1]} 
                        for c in candidate.detour_coordinates
                    ],
                    'tags': {}  # Would extract from way data
                }
                
                segment_features = await self.segment_extractor.extract_segment_features(
                    [detour_segment], budget
                )
                
                if segment_features:
                    feature = segment_features[0]
                    candidate.segment_features = segment_features
                    
                    # Update scores based on actual features
                    candidate.dirt_gain = feature.dirt_score
                    candidate.scenic_gain = feature.scenic_score
                    candidate.risk_penalty = feature.risk_score
                    candidate.popularity_gain = feature.popularity_score
                    candidate.confidence = 0.8  # Higher confidence with features
            
            # Calculate objective gain using route weights
            objective_gain = (
                candidate.dirt_gain * max(0, route_weights.dirt) +
                candidate.scenic_gain * max(0, route_weights.scenic) +
                candidate.popularity_gain * max(0, route_weights.popularity) -
                candidate.risk_penalty * max(0, -route_weights.risk)
            )
            
            candidate.objective_gain = objective_gain
            
            # Calculate efficiency ratio (gain per km added)
            if candidate.detour_distance_km > 0:
                candidate.efficiency_ratio = objective_gain / candidate.detour_distance_km
            
            return candidate
            
        except Exception as e:
            logger.error(f"Single candidate evaluation failed: {e}")
            # Return candidate with low scores
            candidate.objective_gain = 0.0
            candidate.efficiency_ratio = 0.0
            candidate.confidence = 0.1
            return candidate

    async def _select_optimal_detours(self,
                                    candidates: List[DetourCandidate],
                                    constraints: DetourConstraints,
                                    budget: float) -> List[DetourCandidate]:
        """Select optimal set of detours respecting constraints"""
        
        if not candidates:
            return []
        
        selected = []
        total_distance_added = 0.0
        total_time_added = 0.0
        used_km_markers = set()
        
        # Sort candidates by efficiency ratio
        candidates.sort(key=lambda c: c.efficiency_ratio, reverse=True)
        
        for candidate in candidates:
            if len(selected) >= constraints.max_count:
                break
            
            # Check minimum gain threshold
            if candidate.objective_gain < constraints.min_gain:
                continue
            
            # Check distance penalty constraint
            distance_penalty_pct = (candidate.detour_distance_km - candidate.baseline_distance_km) / candidate.baseline_distance_km * 100
            if distance_penalty_pct > constraints.max_distance_penalty_pct:
                continue
            
            # Check time penalty constraint
            time_penalty_pct = (candidate.detour_duration_min - candidate.baseline_duration_min) / candidate.baseline_duration_min * 100
            if time_penalty_pct > constraints.max_time_penalty_pct:
                continue
            
            # Check total time penalty
            new_total_time = total_time_added + (candidate.detour_duration_min - candidate.baseline_duration_min)
            baseline_total_time = 60  # Assume 1 hour baseline (would calculate from actual route)
            total_time_penalty_pct = new_total_time / baseline_total_time * 100
            if total_time_penalty_pct > constraints.max_total_time_penalty_pct:
                continue
            
            # Check for conflicts with already selected detours
            km_marker = candidate.baseline_km_marker
            conflict = any(abs(km_marker - used_marker) < constraints.sample_km for used_marker in used_km_markers)
            if conflict:
                continue
            
            # Accept this detour
            selected.append(candidate)
            total_distance_added += candidate.detour_distance_km - candidate.baseline_distance_km
            total_time_added += candidate.detour_duration_min - candidate.baseline_duration_min
            used_km_markers.add(km_marker)
        
        logger.info(f"Selected {len(selected)} detours from {len(candidates)} candidates")
        return selected

    async def _build_enhanced_route(self,
                                  baseline_route: Dict[str, Any],
                                  detours: List[DetourCandidate]) -> Dict[str, Any]:
        """Build enhanced route incorporating selected detours"""
        
        # For now, return enhanced baseline with detour metadata
        # In full implementation, would rebuild route geometry with detours inserted
        
        enhanced_route = baseline_route.copy()
        
        # Add detour metadata
        enhanced_route['detours'] = [
            {
                'detour_id': d.detour_id,
                'type': d.detour_type.value,
                'baseline_km': d.baseline_km_marker,
                'distance_km': d.detour_distance_km,
                'dirt_gain': d.dirt_gain,
                'scenic_gain': d.scenic_gain,
                'objective_gain': d.objective_gain
            }
            for d in detours
        ]
        
        # Update route metrics
        if 'distance_m' in enhanced_route:
            added_distance_m = sum(d.detour_distance_km * 1000 for d in detours)
            enhanced_route['distance_m'] += added_distance_m
        
        if 'duration_s' in enhanced_route:
            added_duration_s = sum(d.detour_duration_min * 60 for d in detours)
            enhanced_route['duration_s'] += added_duration_s
        
        return enhanced_route

    def _create_optimization_result(self,
                                  baseline_route: Dict[str, Any],
                                  enhanced_route: Dict[str, Any],
                                  accepted_detours: List[DetourCandidate],
                                  all_candidates: List[DetourCandidate],
                                  optimization_time: float,
                                  constraints: DetourConstraints,
                                  sampling_points: List[Dict[str, Any]]) -> DetourOptimizationResult:
        """Create comprehensive optimization result"""
        
        rejected_detours = [c for c in all_candidates if c not in accepted_detours]
        
        # Calculate summary metrics
        total_dirt_gain = sum(d.dirt_gain for d in accepted_detours)
        total_scenic_gain = sum(d.scenic_gain for d in accepted_detours)
        total_risk_penalty = sum(d.risk_penalty for d in accepted_detours)
        total_distance_added = sum(d.detour_distance_km - d.baseline_distance_km for d in accepted_detours)
        total_time_added = sum(d.detour_duration_min - d.baseline_duration_min for d in accepted_detours)
        
        return DetourOptimizationResult(
            accepted_detours=accepted_detours,
            rejected_detours=rejected_detours,
            baseline_route=baseline_route,
            enhanced_route=enhanced_route,
            total_dirt_gain=total_dirt_gain,
            total_scenic_gain=total_scenic_gain,
            total_risk_penalty=total_risk_penalty,
            total_distance_added_km=total_distance_added,
            total_time_added_min=total_time_added,
            sampling_points=len(sampling_points),
            candidates_evaluated=len(all_candidates),
            optimization_time_s=optimization_time,
            constraints_applied=constraints
        )

    def _create_no_detours_result(self,
                                baseline_route: Dict[str, Any],
                                constraints: DetourConstraints,
                                optimization_time: float) -> DetourOptimizationResult:
        """Create result when no detours are found/accepted"""
        
        return DetourOptimizationResult(
            accepted_detours=[],
            rejected_detours=[],
            baseline_route=baseline_route,
            enhanced_route=baseline_route,
            total_dirt_gain=0.0,
            total_scenic_gain=0.0,
            total_risk_penalty=0.0,
            total_distance_added_km=0.0,
            total_time_added_min=0.0,
            sampling_points=0,
            candidates_evaluated=0,
            optimization_time_s=optimization_time,
            constraints_applied=constraints
        )

    def _find_closest_point_on_line(self,
                                   point: Tuple[float, float],
                                   line_coords: List[Tuple[float, float]]) -> Tuple[Tuple[float, float], int]:
        """Find closest point on a line to a given point"""
        
        min_distance = float('inf')
        closest_point = line_coords[0]
        closest_idx = 0
        
        for i, coord in enumerate(line_coords):
            distance = self._haversine_km(point[1], point[0], coord[1], coord[0])
            if distance < min_distance:
                min_distance = distance
                closest_point = coord
                closest_idx = i
        
        return closest_point, closest_idx

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in kilometers"""
        R = 6371.0  # Earth radius in km
        
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = (math.sin(dlat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c