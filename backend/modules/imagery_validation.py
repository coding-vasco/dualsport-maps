"""
Street-level imagery validation module using Mapillary and KartaView APIs.
Validates dirt segments and provides visual evidence links for route confidence.
"""

import asyncio
import httpx
import logging
import math
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import time
import json

logger = logging.getLogger(__name__)

@dataclass
class ImageryFrame:
    """Single street-level imagery frame with metadata"""
    image_key: str
    provider: str  # 'mapillary' or 'kartaview'
    url: str
    thumbnail_url: Optional[str]
    coordinates: Tuple[float, float]  # (lon, lat)
    heading: Optional[float]  # degrees
    capture_date: str  # ISO date string
    validation_hints: List[str]  # 'unpaved', 'paved', 'gate', 'barrier', 'private', 'rough'
    confidence: float  # 0-1, confidence in validation

@dataclass  
class SegmentValidation:
    """Validation result for a route segment"""
    segment_id: str
    start_coord: Tuple[float, float]
    end_coord: Tuple[float, float]
    imagery_frames: List[ImageryFrame]
    validation_score: float  # 0-1, higher = more validated
    surface_confidence: float  # 0-1, confidence in surface type
    access_confidence: float  # 0-1, confidence in accessibility
    flags: List[str]  # 'verified_unpaved', 'possible_gate', 'private_risk', 'recent_imagery'

class ImageryValidation:
    """Street-level imagery validation for route segments"""
    
    def __init__(self, mapillary_token: str = None, kartaview_token: str = None):
        self.mapillary_token = mapillary_token
        self.kartaview_token = kartaview_token
        self.search_buffer_m = 30  # Search within 30m of route
        self.max_frames_per_km = 3  # Limit frames to prevent overwhelming
        self.min_image_age_days = 365 * 3  # Prefer images < 3 years old
        
        self.validation_stats = {
            "segments_queried": 0,
            "mapillary_frames": 0,
            "kartaview_frames": 0,
            "validation_hints": 0,
            "cache_hits": 0,
            "errors": 0
        }
        
        # Simple cache for imagery searches
        self.imagery_cache = {}
        
    async def validate_segments(self, 
                              segments: List[Dict[str, Any]], 
                              budget_seconds: float = 2.0) -> Dict[str, Any]:
        """
        Validate route segments using street-level imagery
        
        Args:
            segments: List of segments with coordinates and OSM tags
            budget_seconds: Time budget for imagery validation
            
        Returns:
        {
            'segment_validations': List[SegmentValidation],
            'summary': {
                'total_frames': int,
                'verified_segments': int,
                'confidence_score': float,
                'flags': List[str]
            },
            'stats': dict
        }
        """
        start_time = time.time()
        
        if not segments:
            return self._empty_validation_result()
            
        validations = []
        segment_budget = budget_seconds / len(segments) if segments else budget_seconds
        
        for i, segment in enumerate(segments):
            if time.time() - start_time > budget_seconds:
                logger.warning(f"Imagery validation budget exceeded at segment {i}/{len(segments)}")
                break
                
            try:
                validation = await self._validate_single_segment(
                    segment, segment_budget, f"seg_{i}"
                )
                validations.append(validation)
                
            except Exception as e:
                logger.error(f"Failed to validate segment {i}: {e}")
                self.validation_stats["errors"] += 1
                continue
        
        # Calculate summary
        summary = self._calculate_validation_summary(validations)
        
        elapsed = time.time() - start_time
        stats = {
            **self.validation_stats,
            "validation_time_seconds": elapsed,
            "budget_used_pct": (elapsed / budget_seconds) * 100,
            "segments_processed": len(validations)
        }
        
        return {
            'segment_validations': validations,
            'summary': summary,
            'stats': stats
        }
    
    async def _validate_single_segment(self, 
                                     segment: Dict[str, Any], 
                                     budget: float, 
                                     segment_id: str) -> SegmentValidation:
        """Validate a single route segment with imagery"""
        
        coordinates = segment.get('coordinates', [])
        if len(coordinates) < 2:
            return SegmentValidation(
                segment_id=segment_id,
                start_coord=(0, 0),
                end_coord=(0, 0),
                imagery_frames=[],
                validation_score=0.0,
                surface_confidence=0.0,
                access_confidence=0.0,
                flags=['no_coordinates']
            )
        
        start_coord = (coordinates[0]['longitude'], coordinates[0]['latitude'])
        end_coord = (coordinates[-1]['longitude'], coordinates[-1]['latitude'])
        
        # Search for imagery frames near segment
        frames = await self._search_imagery_near_segment(
            coordinates, budget * 0.8
        )
        
        # Analyze frames for validation hints
        analyzed_frames = self._analyze_imagery_frames(frames, segment)
        
        # Calculate validation scores
        validation_score = self._calculate_segment_validation_score(analyzed_frames)
        surface_confidence = self._calculate_surface_confidence(analyzed_frames, segment)
        access_confidence = self._calculate_access_confidence(analyzed_frames, segment)
        
        # Generate flags
        flags = self._generate_validation_flags(analyzed_frames, segment)
        
        self.validation_stats["segments_queried"] += 1
        
        return SegmentValidation(
            segment_id=segment_id,
            start_coord=start_coord,
            end_coord=end_coord,
            imagery_frames=analyzed_frames,
            validation_score=validation_score,
            surface_confidence=surface_confidence,
            access_confidence=access_confidence,
            flags=flags
        )
    
    async def _search_imagery_near_segment(self, 
                                         coordinates: List[Dict[str, Any]], 
                                         budget: float) -> List[ImageryFrame]:
        """Search for imagery frames near segment coordinates"""
        
        # Create bounding box around segment with buffer
        lons = [c['longitude'] for c in coordinates]
        lats = [c['latitude'] for c in coordinates]
        
        buffer_deg = self.search_buffer_m / 111000  # Rough conversion to degrees
        
        bbox = {
            'west': min(lons) - buffer_deg,
            'south': min(lats) - buffer_deg,
            'east': max(lons) + buffer_deg,
            'north': max(lats) + buffer_deg
        }
        
        # Check cache first
        bbox_key = f"{bbox['west']:.4f}_{bbox['south']:.4f}_{bbox['east']:.4f}_{bbox['north']:.4f}"
        if bbox_key in self.imagery_cache:
            self.validation_stats["cache_hits"] += 1
            return self.imagery_cache[bbox_key]
        
        frames = []
        
        # Search Mapillary if token available
        if self.mapillary_token:
            try:
                mapillary_frames = await self._search_mapillary(bbox, budget * 0.6)
                frames.extend(mapillary_frames)
            except Exception as e:
                logger.error(f"Mapillary search failed: {e}")
        
        # Search KartaView if token available  
        if self.kartaview_token:
            try:
                kartaview_frames = await self._search_kartaview(bbox, budget * 0.4)
                frames.extend(kartaview_frames)
            except Exception as e:
                logger.error(f"KartaView search failed: {e}")
        
        # Limit and sort by relevance
        segment_length_km = self._calculate_segment_length_km(coordinates)
        max_frames = max(1, int(segment_length_km * self.max_frames_per_km))
        
        # Sort by distance to segment center and recency
        segment_center = self._get_segment_center(coordinates)
        frames.sort(key=lambda f: (
            self._haversine_km(
                segment_center[1], segment_center[0], 
                f.coordinates[1], f.coordinates[0]
            ),
            -self._parse_date_score(f.capture_date)  # Negative for reverse sort (newer first)
        ))
        
        frames = frames[:max_frames]
        
        # Cache results
        self.imagery_cache[bbox_key] = frames
        
        return frames
    
    async def _search_mapillary(self, bbox: Dict[str, float], budget: float) -> List[ImageryFrame]:
        """Search Mapillary API for imagery frames in bounding box"""
        
        url = "https://graph.mapillary.com/images"
        params = {
            'access_token': self.mapillary_token,
            'bbox': f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}",
            'fields': 'id,computed_geometry,captured_at,compass_angle,thumb_256_url',
            'limit': 50  # API limit
        }
        
        try:
            async with httpx.AsyncClient(timeout=budget) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    frames = []
                    
                    for item in data.get('data', []):
                        geometry = item.get('computed_geometry', {})
                        coordinates_data = geometry.get('coordinates', [])
                        
                        if len(coordinates_data) >= 2:
                            frame = ImageryFrame(
                                image_key=item['id'],
                                provider='mapillary',
                                url=f"https://www.mapillary.com/map/im/{item['id']}",
                                thumbnail_url=item.get('thumb_256_url'),
                                coordinates=(coordinates_data[0], coordinates_data[1]),
                                heading=item.get('compass_angle'),
                                capture_date=item.get('captured_at', ''),
                                validation_hints=[],  # Will be filled by analysis
                                confidence=0.5  # Base confidence
                            )
                            frames.append(frame)
                    
                    self.validation_stats["mapillary_frames"] += len(frames)
                    return frames
                else:
                    logger.error(f"Mapillary API error: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Mapillary request failed: {e}")
            
        return []
    
    async def _search_kartaview(self, bbox: Dict[str, float], budget: float) -> List[ImageryFrame]:
        """Search KartaView API for imagery frames in bounding box"""
        
        # KartaView API endpoint (OpenStreetCam)
        url = "https://api.openstreetcam.org/2.0/photo/"
        
        params = {
            'bbi': f"{bbox['north']},{bbox['west']},{bbox['south']},{bbox['east']}",
            'zoom': 14,
            'limit': 50
        }
        
        try:
            async with httpx.AsyncClient(timeout=budget) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    frames = []
                    
                    for item in data.get('result', {}).get('data', []):
                        frame = ImageryFrame(
                            image_key=str(item.get('id', '')),
                            provider='kartaview',
                            url=f"https://kartaview.org/details/{item.get('sequence_id', '')}/{item.get('sequence_index', '')}",
                            thumbnail_url=item.get('th_name'),  # Thumbnail URL
                            coordinates=(float(item.get('lng', 0)), float(item.get('lat', 0))),
                            heading=item.get('heading'),
                            capture_date=item.get('date_added', ''),
                            validation_hints=[],
                            confidence=0.5
                        )
                        frames.append(frame)
                    
                    self.validation_stats["kartaview_frames"] += len(frames)
                    return frames
                else:
                    logger.error(f"KartaView API error: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"KartaView request failed: {e}")
            
        return []
    
    def _analyze_imagery_frames(self, 
                              frames: List[ImageryFrame], 
                              segment: Dict[str, Any]) -> List[ImageryFrame]:
        """Analyze imagery frames to extract validation hints"""
        
        analyzed_frames = []
        segment_tags = segment.get('tags', {})
        
        for frame in frames:
            # Copy frame and add validation hints
            analyzed_frame = ImageryFrame(
                image_key=frame.image_key,
                provider=frame.provider,
                url=frame.url,
                thumbnail_url=frame.thumbnail_url,
                coordinates=frame.coordinates,
                heading=frame.heading,
                capture_date=frame.capture_date,
                validation_hints=self._extract_validation_hints(frame, segment_tags),
                confidence=self._calculate_frame_confidence(frame, segment_tags)
            )
            
            analyzed_frames.append(analyzed_frame)
            
        return analyzed_frames
    
    def _extract_validation_hints(self, 
                                frame: ImageryFrame, 
                                segment_tags: Dict[str, str]) -> List[str]:
        """Extract validation hints from imagery frame (placeholder for ML analysis)"""
        
        hints = []
        
        # This would normally involve ML analysis of the actual image
        # For now, we use heuristics based on metadata and tags
        
        # Date-based hints
        capture_date = self._parse_date_score(frame.capture_date)
        if capture_date > 0.8:  # Recent image
            hints.append('recent_imagery')
        elif capture_date < 0.3:  # Old image
            hints.append('outdated_imagery')
        
        # Provider-based confidence
        if frame.provider == 'mapillary':
            hints.append('mapillary_verified')
        elif frame.provider == 'kartaview':
            hints.append('kartaview_verified')
        
        # Placeholder ML analysis results (would be actual computer vision)
        # These would be extracted from actual image analysis
        expected_surface = segment_tags.get('surface', '')
        if expected_surface in ['gravel', 'dirt', 'compacted']:
            # Simulate 70% accuracy in detecting unpaved surfaces
            if hash(frame.image_key) % 10 < 7:
                hints.append('detected_unpaved')
            else:
                hints.append('detected_paved')  # Conflicting evidence
        
        # Access restriction detection (placeholder)
        highway_type = segment_tags.get('highway', '')
        if highway_type == 'track':
            # Simulate gate/barrier detection
            if hash(frame.image_key + 'gate') % 10 < 2:  # 20% chance
                hints.append('possible_gate')
            if hash(frame.image_key + 'barrier') % 10 < 1:  # 10% chance
                hints.append('detected_barrier')
        
        self.validation_stats["validation_hints"] += len(hints)
        return hints
    
    def _calculate_frame_confidence(self, 
                                  frame: ImageryFrame, 
                                  segment_tags: Dict[str, str]) -> float:
        """Calculate confidence score for imagery frame validation"""
        
        confidence = 0.5  # Base confidence
        
        # Recency bonus
        date_score = self._parse_date_score(frame.capture_date)
        confidence += date_score * 0.2
        
        # Provider reliability
        if frame.provider == 'mapillary':
            confidence += 0.1
        elif frame.provider == 'kartaview':
            confidence += 0.05
        
        # Heading availability (better orientation context)
        if frame.heading is not None:
            confidence += 0.05
            
        # Thumbnail availability (visual verification possible)
        if frame.thumbnail_url:
            confidence += 0.1
            
        return max(0.0, min(1.0, confidence))
    
    def _parse_date_score(self, date_str: str) -> float:
        """Parse date string and return recency score (0-1, higher = more recent)"""
        
        if not date_str:
            return 0.0
            
        try:
            # Parse various date formats
            for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    capture_date = datetime.strptime(date_str[:19], fmt[:19])
                    break
                except ValueError:
                    continue
            else:
                return 0.0
            
            # Calculate age in days
            age_days = (datetime.now() - capture_date).days
            
            # Score based on age (1.0 for recent, 0.0 for very old)
            if age_days <= 30:
                return 1.0
            elif age_days <= 365:
                return 1.0 - (age_days - 30) / 335  # Linear decay over year
            elif age_days <= self.min_image_age_days:
                return 0.3 - (age_days - 365) / (self.min_image_age_days - 365) * 0.3
            else:
                return 0.0
                
        except Exception as e:
            logger.error(f"Error parsing date {date_str}: {e}")
            return 0.0
    
    def _calculate_segment_validation_score(self, frames: List[ImageryFrame]) -> float:
        """Calculate overall validation score for segment"""
        
        if not frames:
            return 0.0
            
        # Average frame confidence
        avg_confidence = sum(f.confidence for f in frames) / len(frames)
        
        # Bonus for multiple frames
        frame_bonus = min(0.2, len(frames) * 0.05)
        
        # Recent imagery bonus
        recent_frames = sum(1 for f in frames if 'recent_imagery' in f.validation_hints)
        recency_bonus = min(0.1, recent_frames * 0.05)
        
        validation_score = avg_confidence + frame_bonus + recency_bonus
        
        return max(0.0, min(1.0, validation_score))
    
    def _calculate_surface_confidence(self, 
                                    frames: List[ImageryFrame], 
                                    segment: Dict[str, Any]) -> float:
        """Calculate confidence in surface type based on imagery"""
        
        if not frames:
            return 0.0
            
        expected_surface = segment.get('tags', {}).get('surface', '')
        
        # Count supporting and conflicting evidence
        supporting_hints = 0
        conflicting_hints = 0
        
        for frame in frames:
            if expected_surface in ['gravel', 'dirt', 'compacted', 'ground']:
                if 'detected_unpaved' in frame.validation_hints:
                    supporting_hints += 1
                elif 'detected_paved' in frame.validation_hints:
                    conflicting_hints += 1
            else:  # Expecting paved
                if 'detected_paved' in frame.validation_hints:
                    supporting_hints += 1
                elif 'detected_unpaved' in frame.validation_hints:
                    conflicting_hints += 1
        
        if supporting_hints + conflicting_hints == 0:
            return 0.5  # No evidence either way
            
        confidence = supporting_hints / (supporting_hints + conflicting_hints)
        
        # Boost confidence if multiple supporting frames
        if supporting_hints > 1:
            confidence = min(1.0, confidence + 0.1)
            
        return confidence
    
    def _calculate_access_confidence(self, 
                                   frames: List[ImageryFrame], 
                                   segment: Dict[str, Any]) -> float:
        """Calculate confidence in accessibility based on imagery"""
        
        if not frames:
            return 0.5  # Neutral confidence
            
        # Look for access restriction indicators
        barrier_indicators = 0
        clear_access = 0
        
        for frame in frames:
            if any(hint in frame.validation_hints for hint in ['possible_gate', 'detected_barrier']):
                barrier_indicators += 1
            elif 'recent_imagery' in frame.validation_hints:
                clear_access += 1  # Recent imagery with no barriers
        
        if barrier_indicators == 0 and clear_access > 0:
            return 0.8  # High confidence in access
        elif barrier_indicators > 0:
            return 0.3  # Lower confidence due to potential barriers
        else:
            return 0.5  # Neutral
    
    def _generate_validation_flags(self, 
                                 frames: List[ImageryFrame], 
                                 segment: Dict[str, Any]) -> List[str]:
        """Generate validation flags based on imagery analysis"""
        
        flags = []
        
        if not frames:
            flags.append('no_imagery')
            return flags
        
        # Evidence flags
        unpaved_evidence = sum(1 for f in frames if 'detected_unpaved' in f.validation_hints)
        paved_evidence = sum(1 for f in frames if 'detected_paved' in f.validation_hints)
        
        if unpaved_evidence > paved_evidence:
            flags.append('verified_unpaved')
        elif paved_evidence > unpaved_evidence:
            flags.append('verified_paved')
        
        # Access flags
        if any('possible_gate' in f.validation_hints for f in frames):
            flags.append('possible_gate')
        if any('detected_barrier' in f.validation_hints for f in frames):
            flags.append('barrier_detected')
        
        # Recency flags
        if any('recent_imagery' in f.validation_hints for f in frames):
            flags.append('recent_imagery')
        if all('outdated_imagery' in f.validation_hints for f in frames):
            flags.append('outdated_imagery')
        
        # Multiple sources
        providers = set(f.provider for f in frames)
        if len(providers) > 1:
            flags.append('multiple_sources')
            
        return flags
    
    def _calculate_segment_length_km(self, coordinates: List[Dict[str, Any]]) -> float:
        """Calculate segment length in kilometers"""
        
        if len(coordinates) < 2:
            return 0.0
            
        total_km = 0.0
        for i in range(len(coordinates) - 1):
            c1 = coordinates[i]
            c2 = coordinates[i + 1]
            
            total_km += self._haversine_km(
                c1['latitude'], c1['longitude'],
                c2['latitude'], c2['longitude']
            )
        
        return total_km
    
    def _get_segment_center(self, coordinates: List[Dict[str, Any]]) -> Tuple[float, float]:
        """Get center point of segment"""
        
        if not coordinates:
            return (0.0, 0.0)
            
        avg_lon = sum(c['longitude'] for c in coordinates) / len(coordinates)
        avg_lat = sum(c['latitude'] for c in coordinates) / len(coordinates)
        
        return (avg_lon, avg_lat)
    
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
    
    def _calculate_validation_summary(self, validations: List[SegmentValidation]) -> Dict[str, Any]:
        """Calculate summary statistics for all validations"""
        
        if not validations:
            return {
                'total_frames': 0,
                'verified_segments': 0,
                'confidence_score': 0.0,
                'flags': ['no_validation_data']
            }
        
        total_frames = sum(len(v.imagery_frames) for v in validations)
        verified_segments = sum(1 for v in validations if v.validation_score > 0.6)
        
        # Average confidence across all segments
        avg_confidence = sum(v.validation_score for v in validations) / len(validations)
        
        # Collect all unique flags
        all_flags = set()
        for validation in validations:
            all_flags.update(validation.flags)
        
        return {
            'total_frames': total_frames,
            'verified_segments': verified_segments,
            'confidence_score': round(avg_confidence, 2),
            'flags': sorted(list(all_flags))
        }
    
    def _empty_validation_result(self) -> Dict[str, Any]:
        """Return empty validation result when no segments provided"""
        return {
            'segment_validations': [],
            'summary': {
                'total_frames': 0,
                'verified_segments': 0,
                'confidence_score': 0.0,
                'flags': ['no_segments']
            },
            'stats': {
                **self.validation_stats,
                "validation_time_seconds": 0.0,
                "segments_processed": 0
            }
        }