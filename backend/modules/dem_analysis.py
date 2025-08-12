"""
Digital Elevation Model (DEM) analysis module for grade computation and ridge preference.
Integrates with Mapbox Terrain-RGB tiles or SRTM data for elevation-aware routing.
"""

import asyncio
import httpx
import logging
import math
import struct
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
import numpy as np
from PIL import Image
import io
import time

logger = logging.getLogger(__name__)

@dataclass
class ElevationPoint:
    """Single elevation measurement point"""
    lon: float
    lat: float
    elevation_m: float
    source: str  # 'mapbox' or 'srtm'
    
@dataclass
class GradeSegment:
    """Road segment with grade analysis"""
    start_coord: Tuple[float, float]
    end_coord: Tuple[float, float]
    length_m: float
    elevation_start: float
    elevation_end: float
    avg_grade_pct: float
    max_grade_pct: float
    slope_variance: float
    ridge_score: float  # 0-1, higher = more scenic ridge-like
    flags: List[str]    # 'super_steep', 'washout_risk', 'scenic_elevation'

class DEMAnalysis:
    """DEM-based elevation and grade analysis for ADV routing"""
    
    def __init__(self, mapbox_token: str = None, use_srtm: bool = False):
        self.mapbox_token = mapbox_token
        self.use_srtm = use_srtm
        self.tile_cache = {}  # Simple in-memory cache
        self.sample_interval_m = 100  # Sample every 100m along route
        self.super_steep_threshold = 15.0  # % grade
        self.washout_grade_threshold = 12.0  # % grade
        self.scenic_elevation_min = 500  # meters
        
        self.analysis_stats = {
            "tiles_fetched": 0,
            "elevation_samples": 0,
            "segments_analyzed": 0,
            "cache_hits": 0,
            "errors": 0
        }
    
    async def analyze_route_grades(self, 
                                 route_coordinates: List[Tuple[float, float]],
                                 surface_tags: List[Dict[str, str]] = None,
                                 budget_seconds: float = 3.0) -> Dict[str, Any]:
        """
        Analyze elevation profile and grades for route coordinates
        
        Args:
            route_coordinates: List of (lon, lat) points
            surface_tags: Optional OSM tags per coordinate for context
            budget_seconds: Time budget for analysis
            
        Returns:
        {
            'elevation_profile': List[ElevationPoint],
            'grade_segments': List[GradeSegment], 
            'summary': {
                'total_ascent_m': float,
                'total_descent_m': float,
                'max_grade_pct': float,
                'avg_grade_pct': float,
                'ridge_score': float,
                'flags': List[str]
            },
            'stats': dict
        }
        """
        start_time = time.time()
        
        if len(route_coordinates) < 2:
            return self._empty_analysis()
            
        # Sample elevations along route
        elevation_points = await self._sample_elevations(
            route_coordinates, budget_seconds * 0.7
        )
        
        if len(elevation_points) < 2:
            logger.warning("Insufficient elevation data for grade analysis")
            return self._empty_analysis()
        
        # Analyze grades between elevation points
        grade_segments = self._analyze_grade_segments(
            elevation_points, surface_tags or []
        )
        
        # Calculate summary statistics
        summary = self._calculate_elevation_summary(grade_segments)
        
        elapsed = time.time() - start_time
        stats = {
            **self.analysis_stats,
            "analysis_time_seconds": elapsed,
            "budget_used_pct": (elapsed / budget_seconds) * 100,
            "coordinates_processed": len(route_coordinates),
            "elevation_points": len(elevation_points),
            "grade_segments": len(grade_segments)
        }
        
        return {
            'elevation_profile': elevation_points,
            'grade_segments': grade_segments,
            'summary': summary,
            'stats': stats
        }
    
    async def _sample_elevations(self, 
                               coordinates: List[Tuple[float, float]], 
                               budget: float) -> List[ElevationPoint]:
        """Sample elevations along coordinate list within time budget"""
        
        # Resample coordinates to target interval
        sampled_coords = self._resample_coordinates(coordinates, self.sample_interval_m)
        
        # Group coordinates by tile for efficient fetching
        tile_groups = self._group_by_tiles(sampled_coords)
        
        elevation_points = []
        tiles_budget = budget / len(tile_groups) if tile_groups else budget
        
        for tile_key, coords_in_tile in tile_groups.items():
            if time.time() - (time.time() - budget) > budget:
                logger.warning("DEM sampling budget exceeded")
                break
                
            try:
                tile_elevations = await self._get_tile_elevations(
                    tile_key, coords_in_tile, tiles_budget
                )
                elevation_points.extend(tile_elevations)
                
            except Exception as e:
                logger.error(f"Failed to get elevations for tile {tile_key}: {e}")
                self.analysis_stats["errors"] += 1
                continue
        
        # Sort by coordinate order
        coord_to_idx = {coord: i for i, coord in enumerate(sampled_coords)}
        elevation_points.sort(key=lambda ep: coord_to_idx.get((ep.lon, ep.lat), 999999))
        
        return elevation_points
    
    def _resample_coordinates(self, 
                            coordinates: List[Tuple[float, float]], 
                            interval_m: float) -> List[Tuple[float, float]]:
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
            
            # Add points at interval along this segment
            while total_distance - last_added_distance >= interval_m:
                # Interpolate position along segment
                distance_into_segment = (last_added_distance + interval_m) - (total_distance - segment_distance)
                ratio = distance_into_segment / segment_distance if segment_distance > 0 else 0
                
                interp_lon = lon1 + (lon2 - lon1) * ratio
                interp_lat = lat1 + (lat2 - lat1) * ratio
                
                resampled.append((interp_lon, interp_lat))
                last_added_distance += interval_m
        
        # Always include end
        if coordinates[-1] not in resampled:
            resampled.append(coordinates[-1])
            
        return resampled
    
    def _group_by_tiles(self, coordinates: List[Tuple[float, float]]) -> Dict[str, List[Tuple[float, float]]]:
        """Group coordinates by elevation tile for batch fetching"""
        tile_groups = {}
        
        for lon, lat in coordinates:
            tile_key = self._get_tile_key(lon, lat, zoom=10)  # Zoom 10 for elevation tiles
            
            if tile_key not in tile_groups:
                tile_groups[tile_key] = []
            tile_groups[tile_key].append((lon, lat))
        
        return tile_groups
    
    def _get_tile_key(self, lon: float, lat: float, zoom: int) -> str:
        """Generate tile key for coordinate at given zoom"""
        # Convert to tile coordinates
        lat_rad = math.radians(lat)
        n = 2.0 ** zoom
        
        xtile = int((lon + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        
        return f"{zoom}_{xtile}_{ytile}"
    
    async def _get_tile_elevations(self, 
                                 tile_key: str,
                                 coordinates: List[Tuple[float, float]], 
                                 budget: float) -> List[ElevationPoint]:
        """Get elevations for coordinates within a single tile"""
        
        # Check cache first
        if tile_key in self.tile_cache:
            self.analysis_stats["cache_hits"] += 1
            elevation_data = self.tile_cache[tile_key]
        else:
            # Fetch tile data
            if self.use_srtm:
                elevation_data = await self._fetch_srtm_tile(tile_key, budget)
            else:
                elevation_data = await self._fetch_mapbox_tile(tile_key, budget)
                
            # Cache for reuse
            if elevation_data:
                self.tile_cache[tile_key] = elevation_data
                self.analysis_stats["tiles_fetched"] += 1
        
        if not elevation_data:
            return []
        
        # Extract elevations for specific coordinates
        elevation_points = []
        for lon, lat in coordinates:
            elevation = self._extract_elevation_at_coordinate(
                lon, lat, elevation_data
            )
            
            if elevation is not None:
                elevation_points.append(ElevationPoint(
                    lon=lon,
                    lat=lat,
                    elevation_m=elevation,
                    source="mapbox" if not self.use_srtm else "srtm"
                ))
                self.analysis_stats["elevation_samples"] += 1
        
        return elevation_points
    
    async def _fetch_mapbox_tile(self, tile_key: str, budget: float) -> Optional[Dict]:
        """Fetch Mapbox Terrain-RGB tile"""
        if not self.mapbox_token:
            logger.warning("No Mapbox token available for DEM analysis")
            return None
            
        zoom, x, y = tile_key.split('_')
        url = f"https://api.mapbox.com/v4/mapbox.terrain-rgb/{zoom}/{x}/{y}@2x.pngraw"
        
        params = {"access_token": self.mapbox_token}
        
        try:
            async with httpx.AsyncClient(timeout=budget) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    # Decode Terrain-RGB image
                    image = Image.open(io.BytesIO(response.content))
                    
                    return {
                        'type': 'mapbox_terrain_rgb',
                        'image': image,
                        'tile_key': tile_key,
                        'bounds': self._tile_to_bounds(zoom, x, y)
                    }
                else:
                    logger.error(f"Mapbox tile fetch failed: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Error fetching Mapbox tile {tile_key}: {e}")
            
        return None
    
    async def _fetch_srtm_tile(self, tile_key: str, budget: float) -> Optional[Dict]:
        """Fetch SRTM elevation data (placeholder - would need SRTM data source)"""
        # This would integrate with AWS SRTM data or local SRTM files
        # For now, return None to fall back to other sources
        logger.info("SRTM integration not implemented, falling back")
        return None
    
    def _extract_elevation_at_coordinate(self, 
                                       lon: float, 
                                       lat: float, 
                                       elevation_data: Dict) -> Optional[float]:
        """Extract elevation at specific coordinate from tile data"""
        
        if elevation_data['type'] == 'mapbox_terrain_rgb':
            return self._extract_mapbox_elevation(lon, lat, elevation_data)
        elif elevation_data['type'] == 'srtm':
            return self._extract_srtm_elevation(lon, lat, elevation_data)
        
        return None
    
    def _extract_mapbox_elevation(self, 
                                lon: float, 
                                lat: float, 
                                tile_data: Dict) -> Optional[float]:
        """Extract elevation from Mapbox Terrain-RGB tile"""
        
        image = tile_data['image']
        bounds = tile_data['bounds']
        
        # Convert lat/lon to pixel coordinates
        west, south, east, north = bounds
        
        if not (west <= lon <= east and south <= lat <= north):
            return None
            
        # Calculate pixel position
        x_ratio = (lon - west) / (east - west)
        y_ratio = (north - lat) / (north - south)  # Note: Y is flipped
        
        pixel_x = int(x_ratio * image.width)
        pixel_y = int(y_ratio * image.height)
        
        # Clamp to image bounds
        pixel_x = max(0, min(image.width - 1, pixel_x))
        pixel_y = max(0, min(image.height - 1, pixel_y))
        
        # Get RGB values
        try:
            r, g, b = image.getpixel((pixel_x, pixel_y))[:3]
            
            # Decode Mapbox Terrain-RGB format
            # elevation = -10000 + ((R * 256 * 256 + G * 256 + B) * 0.1)
            elevation = -10000 + ((r * 65536 + g * 256 + b) * 0.1)
            
            return elevation if elevation > -9999 else None  # Filter invalid values
            
        except Exception as e:
            logger.error(f"Error extracting elevation from pixel: {e}")
            return None
    
    def _tile_to_bounds(self, zoom: str, x: str, y: str) -> Tuple[float, float, float, float]:
        """Convert tile coordinates to lat/lon bounds"""
        zoom, x, y = int(zoom), int(x), int(y)
        n = 2.0 ** zoom
        
        west = x / n * 360.0 - 180.0
        east = (x + 1) / n * 360.0 - 180.0
        
        north_lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        south_lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
        
        return west, south_lat, east, north_lat
    
    def _haversine_m(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in meters"""
        R = 6371000  # Earth radius in meters
        
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
    
    def _analyze_grade_segments(self, 
                              elevation_points: List[ElevationPoint],
                              surface_tags: List[Dict[str, str]]) -> List[GradeSegment]:
        """Analyze grade characteristics between elevation points"""
        
        if len(elevation_points) < 2:
            return []
            
        segments = []
        
        for i in range(len(elevation_points) - 1):
            start_point = elevation_points[i]
            end_point = elevation_points[i + 1]
            
            # Calculate segment metrics
            length_m = self._haversine_m(
                start_point.lat, start_point.lon,
                end_point.lat, end_point.lon
            )
            
            if length_m < 1:  # Skip very short segments
                continue
                
            elevation_diff = end_point.elevation_m - start_point.elevation_m
            avg_grade_pct = (elevation_diff / length_m) * 100
            
            # Calculate slope variance in local window
            slope_variance = self._calculate_slope_variance(
                elevation_points, i, window_size=5
            )
            
            # Calculate ridge score (elevation + low variance = more scenic)
            ridge_score = self._calculate_ridge_score(
                start_point.elevation_m, end_point.elevation_m, slope_variance
            )
            
            # Generate flags for this segment
            surface_info = surface_tags[min(i, len(surface_tags) - 1)] if surface_tags else {}
            flags = self._generate_segment_flags(
                avg_grade_pct, abs(avg_grade_pct), 
                start_point.elevation_m, surface_info
            )
            
            segment = GradeSegment(
                start_coord=(start_point.lon, start_point.lat),
                end_coord=(end_point.lon, end_point.lat),
                length_m=length_m,
                elevation_start=start_point.elevation_m,
                elevation_end=end_point.elevation_m,
                avg_grade_pct=avg_grade_pct,
                max_grade_pct=abs(avg_grade_pct),  # Simplified - could be more sophisticated
                slope_variance=slope_variance,
                ridge_score=ridge_score,
                flags=flags
            )
            
            segments.append(segment)
            self.analysis_stats["segments_analyzed"] += 1
        
        return segments
    
    def _calculate_slope_variance(self, 
                                points: List[ElevationPoint], 
                                center_idx: int, 
                                window_size: int = 5) -> float:
        """Calculate slope variance in local window around point"""
        
        start_idx = max(0, center_idx - window_size // 2)
        end_idx = min(len(points), center_idx + window_size // 2 + 1)
        window_points = points[start_idx:end_idx]
        
        if len(window_points) < 3:
            return 0.0
            
        # Calculate slopes between consecutive points
        slopes = []
        for i in range(len(window_points) - 1):
            p1, p2 = window_points[i], window_points[i + 1]
            
            distance = self._haversine_m(p1.lat, p1.lon, p2.lat, p2.lon)
            if distance > 0:
                slope = (p2.elevation_m - p1.elevation_m) / distance
                slopes.append(slope)
        
        if len(slopes) < 2:
            return 0.0
            
        # Calculate variance
        mean_slope = sum(slopes) / len(slopes)
        variance = sum((s - mean_slope) ** 2 for s in slopes) / len(slopes)
        
        return math.sqrt(variance)  # Standard deviation
    
    def _calculate_ridge_score(self, 
                             elevation_start: float, 
                             elevation_end: float, 
                             slope_variance: float) -> float:
        """Calculate scenic ridge score (0-1, higher = more ridge-like)"""
        
        avg_elevation = (elevation_start + elevation_end) / 2
        
        # Higher elevations are more scenic
        elevation_score = min(1.0, avg_elevation / 1000.0)  # Normalize to 1000m
        
        # Lower slope variance indicates consistent grade (ridge-like)
        variance_score = max(0.0, 1.0 - slope_variance / 10.0)  # Normalize variance
        
        # Combine scores
        ridge_score = (elevation_score * 0.6 + variance_score * 0.4)
        
        return max(0.0, min(1.0, ridge_score))
    
    def _generate_segment_flags(self, 
                              grade_pct: float, 
                              abs_grade_pct: float,
                              elevation: float, 
                              surface_info: Dict[str, str]) -> List[str]:
        """Generate warning/info flags for grade segment"""
        
        flags = []
        
        # Grade-based flags
        if abs_grade_pct > self.super_steep_threshold:
            flags.append("super_steep")
            
        if (abs_grade_pct > self.washout_grade_threshold and 
            surface_info.get("surface") in ["dirt", "gravel", "ground"]):
            flags.append("washout_risk")
            
        # Elevation-based flags
        if elevation > self.scenic_elevation_min:
            flags.append("scenic_elevation")
            
        if elevation > 2000:  # High elevation
            flags.append("high_elevation")
            
        # Surface context flags
        surface = surface_info.get("surface", "")
        if surface == "dirt" and abs_grade_pct > 8:
            flags.append("technical_dirt")
        elif surface in ["gravel", "compacted"] and abs_grade_pct > 10:
            flags.append("technical_gravel")
            
        return flags
    
    def _calculate_elevation_summary(self, segments: List[GradeSegment]) -> Dict[str, Any]:
        """Calculate summary statistics for elevation profile"""
        
        if not segments:
            return {
                'total_ascent_m': 0.0,
                'total_descent_m': 0.0,
                'max_grade_pct': 0.0,
                'avg_grade_pct': 0.0,
                'ridge_score': 0.0,
                'flags': []
            }
        
        total_ascent = sum(max(0, seg.elevation_end - seg.elevation_start) for seg in segments)
        total_descent = sum(max(0, seg.elevation_start - seg.elevation_end) for seg in segments)
        
        max_grade = max(seg.max_grade_pct for seg in segments)
        
        # Weighted average grade by segment length
        total_length = sum(seg.length_m for seg in segments)
        weighted_avg_grade = (sum(seg.avg_grade_pct * seg.length_m for seg in segments) / 
                             total_length if total_length > 0 else 0.0)
        
        # Average ridge score
        avg_ridge_score = sum(seg.ridge_score for seg in segments) / len(segments)
        
        # Collect all unique flags
        all_flags = set()
        for seg in segments:
            all_flags.update(seg.flags)
        
        return {
            'total_ascent_m': round(total_ascent, 1),
            'total_descent_m': round(total_descent, 1),
            'max_grade_pct': round(max_grade, 1),
            'avg_grade_pct': round(weighted_avg_grade, 1),
            'ridge_score': round(avg_ridge_score, 2),
            'flags': sorted(list(all_flags))
        }
    
    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis result when data unavailable"""
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
            'stats': {
                **self.analysis_stats,
                "analysis_time_seconds": 0.0,
                "coordinates_processed": 0,
                "elevation_points": 0,
                "grade_segments": 0
            }
        }