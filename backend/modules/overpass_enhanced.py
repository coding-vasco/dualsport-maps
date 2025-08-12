"""
Enhanced Overpass API module for comprehensive dirt discovery and route anchoring.
Provides robust querying with bbox tiling, retry/backoff, and intelligent anchor placement.
"""

import asyncio
import httpx
import logging
import math
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import time
import random

logger = logging.getLogger(__name__)

@dataclass
class OverpassWay:
    """Represents a discovered way from Overpass with routing metadata"""
    way_id: str
    coordinates: List[Tuple[float, float]]  # [(lon, lat), ...]
    tags: Dict[str, str]
    length_km: float
    surface_score: float  # 0-1, higher = better for ADV
    confidence: float     # 0-1, data quality confidence
    
class OverpassEnhanced:
    """Enhanced Overpass client with ADV-focused dirt discovery"""
    
    def __init__(self, endpoints: List[str] = None, timeout: int = 60):
        self.endpoints = endpoints or [
            "https://overpass-api.de/api/interpreter",
            "https://lz4.overpass-api.de/api/interpreter", 
            "https://z.overpass-api.de/api/interpreter"
        ]
        self.timeout = timeout
        self.max_elements_per_tile = 10000
        self.tile_size = 0.25  # degrees
        self.retry_delays = [1, 2, 4, 8]  # exponential backoff
        self.request_stats = {
            "queries_made": 0,
            "elements_found": 0,
            "tiles_processed": 0,
            "cache_hits": 0,
            "errors": 0
        }
        
    def generate_adv_query(self, bbox: Tuple[float, float, float, float]) -> str:
        """Generate comprehensive Overpass query for ADV routing"""
        south, west, north, east = bbox
        
        query = f"""
        [out:json][timeout:{self.timeout}];
        (
          // Primary ADV tracks - gravel/dirt with good grades
          way
            ["highway"~"^(track|unclassified|service)$"]
            ["surface"~"^(gravel|compacted|fine_gravel|ground|dirt|pebblestone)$"]
            ["tracktype"~"^(grade1|grade2|grade3)$"]
            ({south},{west},{north},{east});
            
          // Secondary tracks - any surface but good smoothness
          way
            ["highway"="track"]
            ["smoothness"!~"^(very_horrible|impassable)$"]
            !["access"~"^(no|private)$"]
            ({south},{west},{north},{east});
            
          // Scenic backroads - paved but low traffic
          way
            ["highway"~"^(unclassified|tertiary|residential)$"]
            ["surface"~"^(asphalt|concrete|paving_stones)$"]
            !["maxspeed"~"^([5-9][0-9]|[0-9]{{3,}})$"]  // Exclude high speed roads
            ({south},{west},{north},{east});
            
          // Known scenic routes
          way
            ["scenic"="yes"]
            ({south},{west},{north},{east});
          way
            ["tourism"="scenic_viewpoint"]
            ({south},{west},{north},{east});
        );
        out geom;
        """
        return query.strip()
    
    async def discover_dirt_corridor(self, 
                                   start_coord: Tuple[float, float],
                                   end_coord: Tuple[float, float],
                                   vias: List[Tuple[float, float]] = None,
                                   budget_seconds: float = 3.0) -> Dict[str, Any]:
        """
        Discover dirt roads and anchor points in corridor between waypoints
        
        Returns:
        {
            'ways': List[OverpassWay],
            'anchor_vias': List[Tuple[float, float, str]],  # (lon, lat, reason)
            'stats': dict,
            'confidence': float
        }
        """
        start_time = time.time()
        vias = vias or []
        all_points = [start_coord] + vias + [end_coord]
        
        # Create corridor bounding box with buffer
        lons = [p[0] for p in all_points]
        lats = [p[1] for p in all_points]
        
        corridor_bbox = (
            min(lats) - 0.02,   # south
            min(lons) - 0.02,   # west  
            max(lats) + 0.02,   # north
            max(lons) + 0.02    # east
        )
        
        # Split into tiles if corridor is large
        tiles = self._generate_bbox_tiles(corridor_bbox)
        logger.info(f"Corridor discovery: {len(tiles)} tiles, budget: {budget_seconds}s")
        
        all_ways = []
        tile_budget = budget_seconds / len(tiles) if tiles else budget_seconds
        
        # Process tiles with budget management
        for i, tile_bbox in enumerate(tiles):
            if time.time() - start_time > budget_seconds:
                logger.warning(f"Overpass budget exceeded, processed {i}/{len(tiles)} tiles")
                break
                
            try:
                ways = await self._query_tile_ways(tile_bbox, tile_budget)
                all_ways.extend(ways)
                
            except Exception as e:
                logger.error(f"Failed to query tile {i}: {e}")
                self.request_stats["errors"] += 1
                continue
        
        # Score and filter ways
        scored_ways = self._score_ways_for_adv(all_ways)
        
        # Generate anchor vias along best ways
        anchor_vias = self._generate_anchor_vias(scored_ways, all_points)
        
        # Calculate corridor confidence
        confidence = self._calculate_corridor_confidence(scored_ways, len(tiles))
        
        elapsed = time.time() - start_time
        stats = {
            **self.request_stats,
            "corridor_tiles": len(tiles),
            "ways_found": len(scored_ways),
            "anchors_generated": len(anchor_vias),
            "query_time_seconds": elapsed,
            "budget_used_pct": (elapsed / budget_seconds) * 100
        }
        
        return {
            'ways': scored_ways,
            'anchor_vias': anchor_vias,
            'stats': stats,
            'confidence': confidence
        }
    
    def _generate_bbox_tiles(self, bbox: Tuple[float, float, float, float]) -> List[Tuple[float, float, float, float]]:
        """Split large bbox into smaller tiles for efficient querying"""
        south, west, north, east = bbox
        
        # Calculate tile counts
        lat_span = north - south
        lon_span = east - west
        
        lat_tiles = max(1, math.ceil(lat_span / self.tile_size))
        lon_tiles = max(1, math.ceil(lon_span / self.tile_size))
        
        tiles = []
        for i in range(lat_tiles):
            for j in range(lon_tiles):
                tile_south = south + i * (lat_span / lat_tiles)
                tile_north = south + (i + 1) * (lat_span / lat_tiles)
                tile_west = west + j * (lon_span / lon_tiles)
                tile_east = west + (j + 1) * (lon_span / lon_tiles)
                
                tiles.append((tile_south, tile_west, tile_north, tile_east))
        
        return tiles[:16]  # Cap at 16 tiles max
    
    async def _query_tile_ways(self, bbox: Tuple[float, float, float, float], budget: float) -> List[Dict]:
        """Query single tile with retry and timeout handling"""
        query = self.generate_adv_query(bbox)
        
        for attempt, delay in enumerate(self.retry_delays):
            if attempt > 0:
                await asyncio.sleep(delay + random.uniform(0, 1))  # jitter
                
            try:
                async with httpx.AsyncClient(timeout=budget) as client:
                    endpoint = self.endpoints[attempt % len(self.endpoints)]
                    
                    response = await client.post(
                        endpoint,
                        data=query,
                        headers={"Content-Type": "application/x-www-form-urlencoded"}
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        ways = [elem for elem in data.get("elements", []) if elem.get("type") == "way"]
                        
                        self.request_stats["queries_made"] += 1
                        self.request_stats["elements_found"] += len(ways)
                        self.request_stats["tiles_processed"] += 1
                        
                        return ways[:self.max_elements_per_tile]  # Cap elements
                        
                    elif response.status_code == 429:  # Rate limited
                        logger.warning(f"Rate limited on attempt {attempt + 1}")
                        continue
                    else:
                        logger.error(f"Overpass error {response.status_code}: {response.text}")
                        
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on tile query attempt {attempt + 1}")
            except Exception as e:
                logger.error(f"Query error on attempt {attempt + 1}: {e}")
        
        # All retries failed
        self.request_stats["errors"] += 1
        return []
    
    def _score_ways_for_adv(self, raw_ways: List[Dict]) -> List[OverpassWay]:
        """Score ways for ADV suitability and convert to OverpassWay objects"""
        scored_ways = []
        
        for way in raw_ways:
            if not way.get("geometry") or len(way.get("geometry", [])) < 2:
                continue
                
            tags = way.get("tags", {})
            geometry = way["geometry"]
            
            # Convert geometry to coordinate list
            coordinates = [(node["lon"], node["lat"]) for node in geometry]
            
            # Calculate way length
            length_km = self._calculate_way_length(coordinates)
            if length_km < 0.1:  # Skip very short ways
                continue
            
            # Score surface suitability for ADV
            surface_score = self._score_surface(tags)
            
            # Calculate confidence based on tag completeness
            confidence = self._calculate_way_confidence(tags)
            
            way_obj = OverpassWay(
                way_id=str(way["id"]),
                coordinates=coordinates,
                tags=tags,
                length_km=length_km,
                surface_score=surface_score,
                confidence=confidence
            )
            
            scored_ways.append(way_obj)
        
        # Sort by surface score descending
        return sorted(scored_ways, key=lambda w: w.surface_score, reverse=True)
    
    def _score_surface(self, tags: Dict[str, str]) -> float:
        """Score surface suitability for adventure motorcycles (0-1)"""
        highway = tags.get("highway", "")
        surface = tags.get("surface", "")
        tracktype = tags.get("tracktype", "")
        smoothness = tags.get("smoothness", "")
        
        score = 0.5  # baseline
        
        # Highway type scoring
        highway_scores = {
            "track": 0.8,
            "unclassified": 0.7,
            "service": 0.6,
            "tertiary": 0.5,
            "residential": 0.4,
            "secondary": 0.3,
            "primary": 0.2,
            "trunk": 0.1,
            "motorway": 0.0
        }
        score += highway_scores.get(highway, 0.3) * 0.3
        
        # Surface type scoring
        surface_scores = {
            "gravel": 0.9,
            "compacted": 0.85,
            "fine_gravel": 0.8,
            "ground": 0.7,
            "dirt": 0.75,
            "pebblestone": 0.6,
            "asphalt": 0.4,
            "concrete": 0.3,
            "paving_stones": 0.35,
            "sand": 0.2,
            "grass": 0.1,
            "mud": 0.05
        }
        score += surface_scores.get(surface, 0.4) * 0.4
        
        # Track type scoring
        tracktype_scores = {
            "grade1": 0.9,   # solid/paved
            "grade2": 0.85,  # mostly solid
            "grade3": 0.7,   # mixed surface
            "grade4": 0.4,   # soft/poor
            "grade5": 0.1    # impassable for vehicles
        }
        if tracktype:
            score += tracktype_scores.get(tracktype, 0.5) * 0.2
        
        # Smoothness penalties
        smoothness_penalties = {
            "excellent": 0.0,
            "good": 0.0,
            "intermediate": 0.0,
            "bad": -0.1,
            "very_bad": -0.2,
            "horrible": -0.3,
            "very_horrible": -0.4,
            "impassable": -0.5
        }
        if smoothness:
            score += smoothness_penalties.get(smoothness, 0.0)
        
        # Special bonuses
        if tags.get("scenic") == "yes":
            score += 0.1
        if tags.get("motor_vehicle") == "no" and highway == "track":
            score += 0.05  # motorcycle-only tracks
            
        return max(0.0, min(1.0, score))
    
    def _calculate_way_length(self, coordinates: List[Tuple[float, float]]) -> float:
        """Calculate way length in kilometers using haversine formula"""
        if len(coordinates) < 2:
            return 0.0
            
        total_km = 0.0
        for i in range(len(coordinates) - 1):
            lon1, lat1 = coordinates[i]
            lon2, lat2 = coordinates[i + 1]
            total_km += self._haversine_km(lat1, lon1, lat2, lon2)
        
        return total_km
    
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
    
    def _calculate_way_confidence(self, tags: Dict[str, str]) -> float:
        """Calculate confidence score based on tag completeness"""
        confidence = 0.5
        
        # Required tags present
        if tags.get("highway"):
            confidence += 0.2
        if tags.get("surface"):
            confidence += 0.2
        if tags.get("tracktype"):
            confidence += 0.1
            
        # Optional but helpful tags
        if tags.get("smoothness"):
            confidence += 0.05
        if tags.get("width"):
            confidence += 0.05
        if tags.get("access"):
            confidence += 0.05
        if tags.get("motor_vehicle"):
            confidence += 0.05
            
        return min(1.0, confidence)
    
    def _generate_anchor_vias(self, ways: List[OverpassWay], route_points: List[Tuple[float, float]]) -> List[Tuple[float, float, str]]:
        """Generate anchor via points along high-scoring ways to steer routing"""
        if len(ways) < 2:
            return []
            
        # Take top scoring ways
        top_ways = ways[:20]  # Limit to best 20 ways
        
        anchors = []
        target_count = min(8, len(top_ways) // 3)  # 3-8 anchors
        
        for i, way in enumerate(top_ways[:target_count]):
            if way.length_km < 1.0:  # Skip short ways
                continue
                
            # Find midpoint of way for anchor placement
            coords = way.coordinates
            mid_idx = len(coords) // 2
            anchor_point = coords[mid_idx]
            
            # Generate reason for this anchor
            reason = self._generate_anchor_reason(way)
            
            anchors.append((anchor_point[0], anchor_point[1], reason))
        
        return anchors
    
    def _generate_anchor_reason(self, way: OverpassWay) -> str:
        """Generate human-readable reason for anchor placement"""
        tags = way.tags
        surface = tags.get("surface", "unknown")
        highway = tags.get("highway", "road")
        tracktype = tags.get("tracktype", "")
        
        reason_parts = []
        
        if surface in ["gravel", "dirt", "compacted"]:
            reason_parts.append(f"{surface}_segment")
        if highway == "track":
            reason_parts.append("dirt_track")
        if tracktype in ["grade1", "grade2"]:
            reason_parts.append("good_surface")
        if tags.get("scenic") == "yes":
            reason_parts.append("scenic_route")
            
        return "_".join(reason_parts) or "adv_waypoint"
    
    def _calculate_corridor_confidence(self, ways: List[OverpassWay], tile_count: int) -> float:
        """Calculate overall confidence in corridor dirt discovery"""
        if not ways:
            return 0.1
            
        # Base confidence from way count and quality
        way_confidence = min(1.0, len(ways) / 10.0)  # More ways = higher confidence
        
        # Average surface score
        avg_surface_score = sum(w.surface_score for w in ways) / len(ways)
        
        # Tag completeness
        avg_tag_confidence = sum(w.confidence for w in ways) / len(ways)
        
        # Penalty for incomplete coverage (many tiles but few ways)
        coverage_penalty = 0.0
        if tile_count > 4 and len(ways) < tile_count * 2:
            coverage_penalty = 0.2
            
        confidence = (way_confidence * 0.4 + 
                     avg_surface_score * 0.3 + 
                     avg_tag_confidence * 0.3 - 
                     coverage_penalty)
        
        return max(0.0, min(1.0, confidence))