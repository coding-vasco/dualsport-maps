"""
Segment Features Module - Phase 2
Unified per-edge feature extraction for advanced ADV route planning.

Features calculated:
- Surface, tracktype, smoothness, road_class (from OSM)
- Grade_%, curvature (from DEM and geometry)
- Coast_distance_km, green_density (from geospatial data)
- Ridge_score (Topographic Position Index)
- Popularity_score, imagery_confidence (from external modules)
- Access_flags, seasonality_hint (from OSM tags)
"""

import asyncio
import logging
import math
import time
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
import numpy as np
from datetime import datetime
import json

logger = logging.getLogger(__name__)

@dataclass
class SegmentFeature:
    """Complete feature set for a single route segment"""
    segment_id: str
    coordinates: List[Tuple[float, float]]  # [(lon, lat), ...]
    length_km: float
    
    # OSM-derived features
    surface: str
    surface_score: float  # 0-1, higher = better for ADV
    tracktype: str
    tracktype_score: float  # 0-1, higher = better surface quality
    smoothness: str
    smoothness_score: float  # 0-1, higher = smoother
    road_class: str
    road_class_score: float  # 0-1, higher = better for ADV
    
    # Geometric features
    curvature_mean: float  # mean(abs(Δbearing)) per km
    curvature_p95: float   # 95th percentile curvature (twisties bursts)
    
    # Elevation features
    grade_mean_pct: float
    grade_p95_pct: float
    pct_over_8_pct: float   # % of segment over 8% grade
    pct_over_12_pct: float  # % of segment over 12% grade
    pct_over_16_pct: float  # % of segment over 16% grade
    
    # Environmental features
    coast_distance_km: float  # min distance to coast/water
    green_density: float      # 0-1, forest/park coverage in 50m buffer
    ridge_score: float        # 0-1, topographic position index
    
    # External data features
    popularity_score: float   # 0-1, combined from multiple sources
    imagery_confidence: float # 0-1, Mapillary/KartaView coverage
    
    # Access and risk features
    access_flags: List[str]   # 'seasonal', 'private', 'bridge_must_use', etc.
    seasonality_hint: str     # 'year_round', 'summer_only', 'spring_fall', etc.
    
    # Composite scores
    dirt_score: float         # 0-1, overall dirt/off-pavement suitability
    scenic_score: float       # 0-1, overall scenic potential
    risk_score: float         # 0-1, overall risk/difficulty

class SegmentFeatureExtractor:
    """Extract comprehensive features for route segments"""
    
    def __init__(self, 
                 dem_analyzer=None,
                 imagery_validator=None,
                 popularity_tracker=None):
        self.dem_analyzer = dem_analyzer
        self.imagery_validator = imagery_validator
        self.popularity_tracker = popularity_tracker
        
        # Feature extraction parameters
        self.curvature_sample_distance_m = 30  # Sample every 30m for curvature
        self.green_buffer_m = 50  # Buffer for green density calculation
        self.ridge_radius_m = 90  # Radius for topographic position index
        
        # Scoring weights for composite scores
        self.dirt_weights = {
            'surface': 0.4,
            'tracktype': 0.3,
            'smoothness': 0.2,
            'road_class': 0.1
        }
        
        self.scenic_weights = {
            'curvature': 0.25,
            'ridge': 0.25,
            'coast': 0.20,
            'green': 0.15,
            'elevation': 0.15
        }
        
        self.risk_weights = {
            'grade': 0.4,
            'surface': 0.3,
            'access': 0.2,
            'seasonal': 0.1
        }
        
        self.extraction_stats = {
            "segments_processed": 0,
            "features_extracted": 0,
            "dem_analyses": 0,
            "curvature_calculations": 0,
            "errors": 0
        }

    async def extract_segment_features(self,
                                     segments: List[Dict[str, Any]],
                                     budget_seconds: float = 10.0) -> List[SegmentFeature]:
        """
        Extract comprehensive features for all segments
        
        Args:
            segments: List of segment dicts with coordinates and OSM tags
            budget_seconds: Time budget for feature extraction
            
        Returns:
            List of SegmentFeature objects with all calculated features
        """
        start_time = time.time()
        
        if not segments:
            return []
        
        logger.info(f"Extracting features for {len(segments)} segments")
        
        # Process segments in parallel batches
        batch_size = min(10, len(segments))  # Process up to 10 segments in parallel
        features = []
        
        for i in range(0, len(segments), batch_size):
            if time.time() - start_time > budget_seconds:
                logger.warning(f"Feature extraction budget exceeded, processed {i}/{len(segments)} segments")
                break
                
            batch = segments[i:i + batch_size]
            batch_budget = (budget_seconds - (time.time() - start_time)) / len(batch)
            
            # Process batch in parallel
            batch_tasks = [
                self._extract_single_segment_features(segment, batch_budget)
                for segment in batch
            ]
            
            try:
                batch_features = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                for feature in batch_features:
                    if isinstance(feature, SegmentFeature):
                        features.append(feature)
                        self.extraction_stats["segments_processed"] += 1
                    elif isinstance(feature, Exception):
                        logger.error(f"Segment feature extraction failed: {feature}")
                        self.extraction_stats["errors"] += 1
                        
            except Exception as e:
                logger.error(f"Batch feature extraction failed: {e}")
                self.extraction_stats["errors"] += len(batch)
        
        elapsed = time.time() - start_time
        logger.info(f"Feature extraction completed: {len(features)} segments in {elapsed:.2f}s")
        
        return features

    async def _extract_single_segment_features(self,
                                             segment: Dict[str, Any],
                                             budget: float) -> SegmentFeature:
        """Extract features for a single segment"""
        
        segment_id = segment.get('segment_id', f"seg_{hash(str(segment))}")
        coordinates = self._extract_coordinates(segment)
        
        if len(coordinates) < 2:
            return self._create_minimal_feature(segment_id, coordinates)
        
        # Calculate basic geometric properties
        length_km = self._calculate_segment_length(coordinates)
        
        # Extract OSM-based features
        osm_features = self._extract_osm_features(segment.get('tags', {}))
        
        # Calculate geometric features
        curvature_features = await self._calculate_curvature_features(coordinates, budget * 0.2)
        
        # Calculate elevation features (if DEM analyzer available)
        elevation_features = await self._calculate_elevation_features(coordinates, budget * 0.3)
        
        # Calculate environmental features
        environmental_features = await self._calculate_environmental_features(coordinates, budget * 0.2)
        
        # Get external data features
        external_features = await self._get_external_features(segment, coordinates, budget * 0.3)
        
        # Calculate composite scores
        composite_scores = self._calculate_composite_scores(
            osm_features, curvature_features, elevation_features, 
            environmental_features, external_features
        )
        
        # Build complete feature object
        feature = SegmentFeature(
            segment_id=segment_id,
            coordinates=coordinates,
            length_km=length_km,
            
            # OSM features
            **osm_features,
            
            # Geometric features
            **curvature_features,
            
            # Elevation features
            **elevation_features,
            
            # Environmental features
            **environmental_features,
            
            # External features
            **external_features,
            
            # Composite scores
            **composite_scores
        )
        
        self.extraction_stats["features_extracted"] += 1
        return feature

    def _extract_coordinates(self, segment: Dict[str, Any]) -> List[Tuple[float, float]]:
        """Extract coordinate list from segment"""
        coordinates = []
        
        if 'coordinates' in segment:
            coords_data = segment['coordinates']
            if isinstance(coords_data, list):
                for coord in coords_data:
                    if isinstance(coord, dict):
                        lon = coord.get('longitude', 0)
                        lat = coord.get('latitude', 0)
                        coordinates.append((lon, lat))
                    elif isinstance(coord, (list, tuple)) and len(coord) >= 2:
                        coordinates.append((coord[0], coord[1]))
        
        return coordinates

    def _calculate_segment_length(self, coordinates: List[Tuple[float, float]]) -> float:
        """Calculate segment length in kilometers"""
        if len(coordinates) < 2:
            return 0.0
            
        total_km = 0.0
        for i in range(len(coordinates) - 1):
            lon1, lat1 = coordinates[i]
            lon2, lat2 = coordinates[i + 1]
            total_km += self._haversine_km(lat1, lon1, lat2, lon2)
        
        return total_km

    def _extract_osm_features(self, tags: Dict[str, str]) -> Dict[str, Any]:
        """Extract and score OSM-based features"""
        
        # Extract basic tags
        surface = tags.get('surface', 'unknown')
        tracktype = tags.get('tracktype', 'unknown')
        smoothness = tags.get('smoothness', 'unknown')
        highway = tags.get('highway', 'unknown')
        
        # Score surface suitability for ADV
        surface_score = self._score_surface_for_adv(surface)
        tracktype_score = self._score_tracktype_for_adv(tracktype)
        smoothness_score = self._score_smoothness_for_adv(smoothness)
        road_class_score = self._score_road_class_for_adv(highway)
        
        return {
            'surface': surface,
            'surface_score': surface_score,
            'tracktype': tracktype,
            'tracktype_score': tracktype_score,
            'smoothness': smoothness,
            'smoothness_score': smoothness_score,
            'road_class': highway,
            'road_class_score': road_class_score
        }

    def _score_surface_for_adv(self, surface: str) -> float:
        """Score surface type for ADV suitability (0-1)"""
        surface_scores = {
            'gravel': 0.95,
            'compacted': 0.90,
            'fine_gravel': 0.85,
            'ground': 0.80,
            'dirt': 0.75,
            'pebblestone': 0.70,
            'asphalt': 0.40,
            'concrete': 0.30,
            'paving_stones': 0.35,
            'cobblestone': 0.25,
            'sand': 0.20,
            'grass': 0.15,
            'mud': 0.05,
            'unknown': 0.50
        }
        return surface_scores.get(surface.lower(), 0.50)

    def _score_tracktype_for_adv(self, tracktype: str) -> float:
        """Score track type for ADV suitability (0-1)"""
        tracktype_scores = {
            'grade1': 0.95,  # Solid/paved
            'grade2': 0.85,  # Mostly solid
            'grade3': 0.70,  # Mixed surface
            'grade4': 0.40,  # Soft/poor
            'grade5': 0.10,  # Impassable for vehicles
            'unknown': 0.60
        }
        return tracktype_scores.get(tracktype.lower(), 0.60)

    def _score_smoothness_for_adv(self, smoothness: str) -> float:
        """Score smoothness for ADV suitability (0-1)"""
        smoothness_scores = {
            'excellent': 1.0,
            'good': 0.9,
            'intermediate': 0.8,
            'bad': 0.6,
            'very_bad': 0.4,
            'horrible': 0.2,
            'very_horrible': 0.1,
            'impassable': 0.0,
            'unknown': 0.7
        }
        return smoothness_scores.get(smoothness.lower(), 0.7)

    def _score_road_class_for_adv(self, highway: str) -> float:
        """Score road class for ADV suitability (0-1)"""
        road_class_scores = {
            'track': 0.95,
            'path': 0.85,
            'unclassified': 0.80,
            'service': 0.75,
            'tertiary': 0.60,
            'residential': 0.50,
            'secondary': 0.30,
            'primary': 0.20,
            'trunk': 0.10,
            'motorway': 0.05,
            'unknown': 0.50
        }
        return road_class_scores.get(highway.lower(), 0.50)

    async def _calculate_curvature_features(self,
                                          coordinates: List[Tuple[float, float]],
                                          budget: float) -> Dict[str, float]:
        """Calculate curvature features from segment geometry"""
        
        if len(coordinates) < 3:
            return {
                'curvature_mean': 0.0,
                'curvature_p95': 0.0
            }
        
        try:
            # Resample coordinates at regular intervals for curvature calculation
            resampled_coords = self._resample_coordinates_by_distance(
                coordinates, self.curvature_sample_distance_m
            )
            
            if len(resampled_coords) < 3:
                return {'curvature_mean': 0.0, 'curvature_p95': 0.0}
            
            # Calculate bearing changes between consecutive segments
            bearing_changes = []
            
            for i in range(1, len(resampled_coords) - 1):
                prev_coord = resampled_coords[i - 1]
                curr_coord = resampled_coords[i]
                next_coord = resampled_coords[i + 1]
                
                # Calculate bearings
                bearing1 = self._calculate_bearing(prev_coord, curr_coord)
                bearing2 = self._calculate_bearing(curr_coord, next_coord)
                
                # Calculate absolute bearing change
                bearing_change = abs(self._normalize_bearing_difference(bearing2 - bearing1))
                bearing_changes.append(bearing_change)
            
            if not bearing_changes:
                return {'curvature_mean': 0.0, 'curvature_p95': 0.0}
            
            # Calculate curvature metrics per km
            segment_length_km = self._calculate_segment_length(coordinates)
            if segment_length_km == 0:
                return {'curvature_mean': 0.0, 'curvature_p95': 0.0}
            
            curvature_mean = (sum(bearing_changes) / len(bearing_changes)) / segment_length_km
            curvature_p95 = np.percentile(bearing_changes, 95) / segment_length_km
            
            self.extraction_stats["curvature_calculations"] += 1
            
            return {
                'curvature_mean': min(curvature_mean, 180.0),  # Cap at 180°/km
                'curvature_p95': min(curvature_p95, 180.0)
            }
            
        except Exception as e:
            logger.error(f"Curvature calculation failed: {e}")
            return {'curvature_mean': 0.0, 'curvature_p95': 0.0}

    def _resample_coordinates_by_distance(self,
                                        coordinates: List[Tuple[float, float]],
                                        distance_m: float) -> List[Tuple[float, float]]:
        """Resample coordinates at regular distance intervals"""
        
        if len(coordinates) < 2:
            return coordinates
            
        resampled = [coordinates[0]]  # Always include start
        
        total_distance = 0.0
        last_added_distance = 0.0
        
        for i in range(len(coordinates) - 1):
            lon1, lat1 = coordinates[i]
            lon2, lat2 = coordinates[i + 1]
            
            segment_distance = self._haversine_m(lat1, lon1, lat2, lon2)
            total_distance += segment_distance
            
            # Add points at regular intervals along this segment
            while total_distance - last_added_distance >= distance_m:
                # Interpolate position along segment
                distance_into_segment = (last_added_distance + distance_m) - (total_distance - segment_distance)
                ratio = distance_into_segment / segment_distance if segment_distance > 0 else 0
                
                interp_lon = lon1 + (lon2 - lon1) * ratio
                interp_lat = lat1 + (lat2 - lat1) * ratio
                
                resampled.append((interp_lon, interp_lat))
                last_added_distance += distance_m
        
        # Always include end
        if coordinates[-1] not in resampled:
            resampled.append(coordinates[-1])
            
        return resampled

    def _calculate_bearing(self, coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """Calculate bearing between two coordinates in degrees"""
        lon1, lat1 = math.radians(coord1[0]), math.radians(coord1[1])
        lon2, lat2 = math.radians(coord2[0]), math.radians(coord2[1])
        
        dlon = lon2 - lon1
        
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        
        bearing = math.atan2(y, x)
        return math.degrees(bearing)

    def _normalize_bearing_difference(self, diff: float) -> float:
        """Normalize bearing difference to [-180, 180] range"""
        while diff > 180:
            diff -= 360
        while diff < -180:
            diff += 360
        return diff

    async def _calculate_elevation_features(self,
                                          coordinates: List[Tuple[float, float]],
                                          budget: float) -> Dict[str, float]:
        """Calculate elevation-based features using DEM analyzer"""
        
        if not self.dem_analyzer:
            return {
                'grade_mean_pct': 0.0,
                'grade_p95_pct': 0.0,
                'pct_over_8_pct': 0.0,
                'pct_over_12_pct': 0.0,
                'pct_over_16_pct': 0.0
            }
        
        try:
            # Use DEM analyzer to get elevation profile
            dem_result = await self.dem_analyzer.analyze_route_grades(
                coordinates, budget_seconds=budget
            )
            
            grade_segments = dem_result.get('grade_segments', [])
            if not grade_segments:
                return {
                    'grade_mean_pct': 0.0,
                    'grade_p95_pct': 0.0,
                    'pct_over_8_pct': 0.0,
                    'pct_over_12_pct': 0.0,
                    'pct_over_16_pct': 0.0
                }
            
            # Extract grade data
            grades = [abs(seg.avg_grade_pct) for seg in grade_segments]
            segment_lengths = [seg.length_m for seg in grade_segments]
            total_length = sum(segment_lengths)
            
            if not grades or total_length == 0:
                return {
                    'grade_mean_pct': 0.0,
                    'grade_p95_pct': 0.0,
                    'pct_over_8_pct': 0.0,
                    'pct_over_12_pct': 0.0,
                    'pct_over_16_pct': 0.0
                }
            
            # Calculate weighted mean grade
            weighted_grades = [grade * length for grade, length in zip(grades, segment_lengths)]
            grade_mean_pct = sum(weighted_grades) / total_length
            
            # Calculate 95th percentile grade
            grade_p95_pct = np.percentile(grades, 95)
            
            # Calculate percentage over thresholds
            pct_over_8 = sum(length for grade, length in zip(grades, segment_lengths) if grade > 8) / total_length * 100
            pct_over_12 = sum(length for grade, length in zip(grades, segment_lengths) if grade > 12) / total_length * 100
            pct_over_16 = sum(length for grade, length in zip(grades, segment_lengths) if grade > 16) / total_length * 100
            
            self.extraction_stats["dem_analyses"] += 1
            
            return {
                'grade_mean_pct': grade_mean_pct,
                'grade_p95_pct': grade_p95_pct,
                'pct_over_8_pct': pct_over_8,
                'pct_over_12_pct': pct_over_12,
                'pct_over_16_pct': pct_over_16
            }
            
        except Exception as e:
            logger.error(f"Elevation feature calculation failed: {e}")
            return {
                'grade_mean_pct': 0.0,
                'grade_p95_pct': 0.0,
                'pct_over_8_pct': 0.0,
                'pct_over_12_pct': 0.0,
                'pct_over_16_pct': 0.0
            }

    async def _calculate_environmental_features(self,
                                              coordinates: List[Tuple[float, float]],
                                              budget: float) -> Dict[str, float]:
        """Calculate environmental features (coast distance, green density, ridge score)"""
        
        # For now, return placeholder values
        # In a full implementation, this would:
        # 1. Query Natural Earth coastline data for coast_distance_km
        # 2. Query OSM for landuse=forest/park within buffer for green_density
        # 3. Calculate Topographic Position Index for ridge_score
        
        return {
            'coast_distance_km': 50.0,  # Placeholder - would calculate actual distance
            'green_density': 0.3,       # Placeholder - would calculate from OSM landuse
            'ridge_score': 0.5          # Placeholder - would calculate TPI from DEM
        }

    async def _get_external_features(self,
                                   segment: Dict[str, Any],
                                   coordinates: List[Tuple[float, float]],
                                   budget: float) -> Dict[str, Any]:
        """Get features from external data sources"""
        
        # Initialize with defaults
        features = {
            'popularity_score': 0.0,
            'imagery_confidence': 0.0,
            'access_flags': [],
            'seasonality_hint': 'unknown'
        }
        
        # Get popularity data if tracker available
        if self.popularity_tracker and budget > 0:
            try:
                # Create minimal bbox around segment
                lons = [c[0] for c in coordinates]
                lats = [c[1] for c in coordinates]
                bbox = (min(lats), min(lons), max(lats), max(lons))
                
                # Convert to way format for popularity tracker
                way_data = [{
                    'way_id': segment.get('segment_id', 'unknown'),
                    'coordinates': [{'longitude': c[0], 'latitude': c[1]} for c in coordinates],
                    'tags': segment.get('tags', {})
                }]
                
                popularity_result = await self.popularity_tracker.analyze_route_popularity(
                    way_data, bbox, budget_seconds=budget * 0.5
                )
                
                way_popularity = popularity_result.get('way_popularity', {})
                if way_popularity:
                    first_way = list(way_popularity.values())[0]
                    features['popularity_score'] = first_way.popularity_score
                    
            except Exception as e:
                logger.error(f"Popularity feature extraction failed: {e}")
        
        # Get imagery data if validator available
        if self.imagery_validator and budget > 0:
            try:
                imagery_segments = [segment]  # Single segment for validation
                
                imagery_result = await self.imagery_validator.validate_segments(
                    imagery_segments, budget_seconds=budget * 0.5
                )
                
                segment_validations = imagery_result.get('segment_validations', [])
                if segment_validations:
                    validation = segment_validations[0]
                    features['imagery_confidence'] = validation.validation_score
                    
            except Exception as e:
                logger.error(f"Imagery feature extraction failed: {e}")
        
        # Extract access and seasonality from OSM tags
        tags = segment.get('tags', {})
        access_flags = self._extract_access_flags(tags)
        seasonality_hint = self._extract_seasonality_hint(tags)
        
        features['access_flags'] = access_flags
        features['seasonality_hint'] = seasonality_hint
        
        return features

    def _extract_access_flags(self, tags: Dict[str, str]) -> List[str]:
        """Extract access restriction flags from OSM tags"""
        flags = []
        
        # Check access restrictions
        if tags.get('access') == 'no':
            flags.append('no_access')
        if tags.get('access') == 'private':
            flags.append('private')
        if tags.get('motor_vehicle') == 'no':
            flags.append('no_motor_vehicle')
            
        # Check for gates and barriers
        if 'gate' in tags or tags.get('barrier') == 'gate':
            flags.append('gate')
        if tags.get('barrier') in ['bollard', 'fence', 'wall']:
            flags.append('barrier')
            
        # Check for seasonal restrictions
        if 'seasonal' in tags.get('access', '').lower():
            flags.append('seasonal')
        if 'winter' in tags.get('note', '').lower():
            flags.append('winter_closure')
            
        return flags

    def _extract_seasonality_hint(self, tags: Dict[str, str]) -> str:
        """Extract seasonality hint from OSM tags"""
        
        # Check for explicit seasonal tags
        if 'seasonal' in tags.get('access', '').lower():
            return 'seasonal'
        if 'winter' in tags.get('access', '').lower():
            return 'summer_only'
        if tags.get('winter_service') == 'no':
            return 'summer_only'
            
        # Check notes for seasonal hints
        note = tags.get('note', '').lower()
        if any(word in note for word in ['winter', 'snow', 'closed']):
            return 'summer_only'
        if any(word in note for word in ['spring', 'fall', 'autumn']):
            return 'spring_fall'
            
        return 'year_round'

    def _calculate_composite_scores(self,
                                  osm_features: Dict[str, Any],
                                  curvature_features: Dict[str, float],
                                  elevation_features: Dict[str, float],
                                  environmental_features: Dict[str, float],
                                  external_features: Dict[str, Any]) -> Dict[str, float]:
        """Calculate composite dirt, scenic, and risk scores"""
        
        # Calculate dirt score (0-1, higher = better for off-pavement)
        dirt_score = (
            osm_features['surface_score'] * self.dirt_weights['surface'] +
            osm_features['tracktype_score'] * self.dirt_weights['tracktype'] +
            osm_features['smoothness_score'] * self.dirt_weights['smoothness'] +
            osm_features['road_class_score'] * self.dirt_weights['road_class']
        )
        
        # Calculate scenic score (0-1, higher = more scenic)
        curvature_normalized = min(curvature_features['curvature_mean'] / 45.0, 1.0)  # Normalize to 45°/km
        ridge_score = environmental_features['ridge_score']
        coast_bonus = max(0, 1.0 - environmental_features['coast_distance_km'] / 10.0)  # Bonus if within 10km of coast
        green_density = environmental_features['green_density']
        elevation_bonus = min(elevation_features['grade_mean_pct'] / 20.0, 0.5)  # Small bonus for elevation variety
        
        scenic_score = (
            curvature_normalized * self.scenic_weights['curvature'] +
            ridge_score * self.scenic_weights['ridge'] +
            coast_bonus * self.scenic_weights['coast'] +
            green_density * self.scenic_weights['green'] +
            elevation_bonus * self.scenic_weights['elevation']
        )
        
        # Calculate risk score (0-1, higher = more risky)
        grade_risk = min(elevation_features['pct_over_12_pct'] / 50.0, 1.0)  # Risk if >50% over 12%
        surface_risk = 1.0 - osm_features['surface_score']  # Inverse of surface quality
        access_risk = len(external_features['access_flags']) / 5.0  # Risk based on access restrictions
        seasonal_risk = 0.3 if external_features['seasonality_hint'] in ['seasonal', 'summer_only'] else 0.0
        
        risk_score = (
            grade_risk * self.risk_weights['grade'] +
            surface_risk * self.risk_weights['surface'] +
            access_risk * self.risk_weights['access'] +
            seasonal_risk * self.risk_weights['seasonal']
        )
        
        return {
            'dirt_score': max(0.0, min(1.0, dirt_score)),
            'scenic_score': max(0.0, min(1.0, scenic_score)),
            'risk_score': max(0.0, min(1.0, risk_score))
        }

    def _create_minimal_feature(self, segment_id: str, coordinates: List[Tuple[float, float]]) -> SegmentFeature:
        """Create minimal feature object when extraction fails"""
        
        return SegmentFeature(
            segment_id=segment_id,
            coordinates=coordinates,
            length_km=0.0,
            
            # OSM features
            surface='unknown',
            surface_score=0.5,
            tracktype='unknown',
            tracktype_score=0.5,
            smoothness='unknown',
            smoothness_score=0.5,
            road_class='unknown',
            road_class_score=0.5,
            
            # Geometric features
            curvature_mean=0.0,
            curvature_p95=0.0,
            
            # Elevation features
            grade_mean_pct=0.0,
            grade_p95_pct=0.0,
            pct_over_8_pct=0.0,
            pct_over_12_pct=0.0,
            pct_over_16_pct=0.0,
            
            # Environmental features
            coast_distance_km=50.0,
            green_density=0.3,
            ridge_score=0.5,
            
            # External features
            popularity_score=0.0,
            imagery_confidence=0.0,
            access_flags=[],
            seasonality_hint='unknown',
            
            # Composite scores
            dirt_score=0.5,
            scenic_score=0.5,
            risk_score=0.5
        )

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

    def _haversine_m(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in meters"""
        return self._haversine_km(lat1, lon1, lat2, lon2) * 1000.0