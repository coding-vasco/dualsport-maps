"""
Popularity tracking module for route segments using community GPX data.
Integrates with Wikiloc, REVER, and other GPX sources to measure route popularity.
"""

import asyncio
import httpx
import logging
import math
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import time
import json
import gpxpy
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class GPXTrace:
    """GPX trace with metadata"""
    trace_id: str
    source: str  # 'wikiloc', 'rever', 'manual', etc.
    coordinates: List[Tuple[float, float]]  # [(lon, lat), ...]
    activity_type: str  # 'motorcycle', 'bicycle', 'hiking', etc.
    upload_date: datetime
    title: str
    tags: List[str]
    popularity_signals: Dict[str, float]  # views, likes, downloads, etc.

@dataclass
class WayPopularity:
    """Popularity data for an OSM way"""
    way_id: str
    coordinates: List[Tuple[float, float]]
    total_hits: int
    motorcycle_hits: int
    recent_hits: int  # Last 2 years
    popularity_score: float  # 0-1 normalized
    last_updated: datetime
    sources: List[str]  # Contributing data sources

class PopularityTracker:
    """Track and analyze route popularity from community GPX sources"""
    
    def __init__(self, wikiloc_token: str = None, rever_token: str = None, db_path: str = None):
        self.wikiloc_token = wikiloc_token
        self.rever_token = rever_token
        self.db_path = db_path or "/tmp/popularity_cache.db"
        
        # Popularity scoring parameters
        self.decay_years = 2.0  # Decay traces older than 2 years
        self.motorcycle_weight = 2.0  # Weight motorcycle traces higher
        self.snap_tolerance_m = 50  # Snap GPX traces within 50m to OSM ways
        
        self.tracking_stats = {
            "traces_processed": 0,
            "ways_updated": 0,
            "wikiloc_queries": 0,
            "rever_queries": 0,
            "map_matches": 0,
            "cache_hits": 0,
            "errors": 0
        }
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database for popularity caching"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Ways popularity table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS way_popularity (
                    way_id TEXT PRIMARY KEY,
                    coordinates TEXT,
                    total_hits INTEGER DEFAULT 0,
                    motorcycle_hits INTEGER DEFAULT 0,
                    recent_hits INTEGER DEFAULT 0,
                    popularity_score REAL DEFAULT 0.0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sources TEXT
                )
            ''')
            
            # GPX traces table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS gpx_traces (
                    trace_id TEXT PRIMARY KEY,
                    source TEXT,
                    coordinates TEXT,
                    activity_type TEXT,
                    upload_date TIMESTAMP,
                    title TEXT,
                    tags TEXT,
                    popularity_signals TEXT,
                    processed BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_way_popularity_score ON way_popularity(popularity_score)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_traces_processed ON gpx_traces(processed)')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to initialize popularity database: {e}")
    
    async def analyze_route_popularity(self, 
                                     route_ways: List[Dict[str, Any]], 
                                     bbox: Tuple[float, float, float, float],
                                     budget_seconds: float = 2.0) -> Dict[str, Any]:
        """
        Analyze popularity for route ways within bounding box
        
        Args:
            route_ways: List of OSM ways with coordinates
            bbox: (south, west, north, east) bounding box
            budget_seconds: Time budget for analysis
            
        Returns:
        {
            'way_popularity': Dict[str, WayPopularity],
            'summary': {
                'avg_popularity': float,
                'total_traces': int,
                'motorcycle_traces': int,
                'coverage_pct': float
            },
            'stats': dict
        }
        """
        start_time = time.time()
        
        if not route_ways:
            return self._empty_popularity_result()
        
        # Get cached popularity data
        cached_popularity = self._get_cached_popularity([w.get('way_id', '') for w in route_ways])
        
        # Determine if we need fresh data
        needs_update = any(
            not cached or 
            (datetime.now() - cached.last_updated).days > 7  # Update weekly
            for cached in cached_popularity.values()
        )
        
        if needs_update and budget_seconds > 0.5:
            # Fetch fresh GPX data
            fresh_traces = await self._fetch_gpx_traces_in_bbox(
                bbox, budget_seconds * 0.7
            )
            
            # Process new traces
            if fresh_traces:
                await self._process_gpx_traces(fresh_traces, route_ways)
                # Refresh cached data
                cached_popularity = self._get_cached_popularity([w.get('way_id', '') for w in route_ways])
        
        # Calculate summary statistics
        summary = self._calculate_popularity_summary(cached_popularity, route_ways)
        
        elapsed = time.time() - start_time
        stats = {
            **self.tracking_stats,
            "analysis_time_seconds": elapsed,
            "budget_used_pct": (elapsed / budget_seconds) * 100,
            "ways_analyzed": len(route_ways),
            "cached_ways": len(cached_popularity)
        }
        
        return {
            'way_popularity': cached_popularity,
            'summary': summary,
            'stats': stats
        }
    
    async def _fetch_gpx_traces_in_bbox(self, 
                                      bbox: Tuple[float, float, float, float], 
                                      budget: float) -> List[GPXTrace]:
        """Fetch GPX traces from all available sources within bounding box"""
        
        south, west, north, east = bbox
        traces = []
        
        # Split budget between sources
        wikiloc_budget = budget * 0.6 if self.wikiloc_token else 0
        rever_budget = budget * 0.4 if self.rever_token else 0
        
        # Fetch from Wikiloc
        if self.wikiloc_token and wikiloc_budget > 0:
            try:
                wikiloc_traces = await self._fetch_wikiloc_traces(
                    bbox, wikiloc_budget
                )
                traces.extend(wikiloc_traces)
            except Exception as e:
                logger.error(f"Wikiloc fetch failed: {e}")
                self.tracking_stats["errors"] += 1
        
        # Fetch from REVER
        if self.rever_token and rever_budget > 0:
            try:
                rever_traces = await self._fetch_rever_traces(
                    bbox, rever_budget
                )
                traces.extend(rever_traces)
            except Exception as e:
                logger.error(f"REVER fetch failed: {e}")
                self.tracking_stats["errors"] += 1
        
        return traces
    
    async def _fetch_wikiloc_traces(self, 
                                  bbox: Tuple[float, float, float, float], 
                                  budget: float) -> List[GPXTrace]:
        """Fetch traces from Wikiloc API"""
        
        south, west, north, east = bbox
        
        # Wikiloc API parameters
        url = "https://www.wikiloc.com/wikiloc/find.do"
        params = {
            'act': 6,  # Motorcycle/Motorbike activity
            'bbox': f"{west},{south},{east},{north}",
            'units': 'metric',
            'limit': 20  # API limit
        }
        
        headers = {
            'Authorization': f'Bearer {self.wikiloc_token}',
            'User-Agent': 'DUALSPORT MAPS/1.0'
        }
        
        try:
            async with httpx.AsyncClient(timeout=budget) as client:
                response = await client.get(url, params=params, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    traces = []
                    
                    for item in data.get('trails', []):
                        # Parse GPX coordinates
                        gpx_url = item.get('gpx_url')
                        if gpx_url:
                            coordinates = await self._download_and_parse_gpx(
                                gpx_url, budget / 20  # Budget per GPX
                            )
                            
                            if coordinates:
                                trace = GPXTrace(
                                    trace_id=f"wikiloc_{item.get('id')}",
                                    source='wikiloc',
                                    coordinates=coordinates,
                                    activity_type='motorcycle',
                                    upload_date=self._parse_wikiloc_date(item.get('date')),
                                    title=item.get('title', ''),
                                    tags=item.get('tags', []),
                                    popularity_signals={
                                        'views': float(item.get('views', 0)),
                                        'likes': float(item.get('likes', 0)),
                                        'downloads': float(item.get('downloads', 0))
                                    }
                                )
                                traces.append(trace)
                    
                    self.tracking_stats["wikiloc_queries"] += 1
                    self.tracking_stats["traces_processed"] += len(traces)
                    
                    return traces
                else:
                    logger.error(f"Wikiloc API error: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Wikiloc request failed: {e}")
            
        return []
    
    async def _fetch_rever_traces(self, 
                                bbox: Tuple[float, float, float, float], 
                                budget: float) -> List[GPXTrace]:
        """Fetch traces from REVER API (if available/licensed)"""
        
        # REVER integration would go here if API access is available
        # For now, return empty list with feature flag
        
        logger.info("REVER integration not available, skipping")
        return []
    
    async def _download_and_parse_gpx(self, gpx_url: str, budget: float) -> List[Tuple[float, float]]:
        """Download and parse GPX file to extract coordinates"""
        
        try:
            async with httpx.AsyncClient(timeout=budget) as client:
                response = await client.get(gpx_url)
                
                if response.status_code == 200:
                    gpx_content = response.text
                    
                    # Parse GPX
                    gpx = gpxpy.parse(gpx_content)
                    coordinates = []
                    
                    for track in gpx.tracks:
                        for segment in track.segments:
                            for point in segment.points:
                                coordinates.append((point.longitude, point.latitude))
                    
                    return coordinates
                    
        except Exception as e:
            logger.error(f"Failed to download/parse GPX {gpx_url}: {e}")
            
        return []
    
    async def _process_gpx_traces(self, traces: List[GPXTrace], route_ways: List[Dict[str, Any]]):
        """Process GPX traces and update way popularity"""
        
        if not traces or not route_ways:
            return
        
        # Create spatial index of route ways for efficient matching
        way_index = self._create_way_spatial_index(route_ways)
        
        # Process each trace
        for trace in traces:
            try:
                # Map-match trace to route ways
                matched_ways = self._map_match_trace_to_ways(trace, way_index)
                
                # Update popularity for matched ways
                self._update_way_popularity(matched_ways, trace)
                
                # Store trace in database
                self._store_gpx_trace(trace)
                
                self.tracking_stats["map_matches"] += len(matched_ways)
                
            except Exception as e:
                logger.error(f"Failed to process trace {trace.trace_id}: {e}")
                self.tracking_stats["errors"] += 1
                continue
    
    def _create_way_spatial_index(self, route_ways: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create simple spatial index for efficient way matching"""
        
        way_index = {}
        
        for way in route_ways:
            way_id = way.get('way_id', '')
            coordinates = way.get('coordinates', [])
            
            if way_id and coordinates:
                # Create bounding box for way
                lons = [c.get('longitude', 0) for c in coordinates]
                lats = [c.get('latitude', 0) for c in coordinates]
                
                bbox = {
                    'way_id': way_id,
                    'coordinates': coordinates,
                    'bbox': (min(lats), min(lons), max(lats), max(lons)),  # south, west, north, east
                    'tags': way.get('tags', {})
                }
                
                way_index[way_id] = bbox
        
        return way_index
    
    def _map_match_trace_to_ways(self, trace: GPXTrace, way_index: Dict[str, Any]) -> List[str]:
        """Map-match GPX trace to OSM ways within snap tolerance"""
        
        matched_ways = set()
        
        # Sample trace points (don't need every point)
        sample_interval = max(1, len(trace.coordinates) // 100)  # Sample ~100 points max
        sampled_points = trace.coordinates[::sample_interval]
        
        for trace_lon, trace_lat in sampled_points:
            # Find ways within snap tolerance
            for way_id, way_data in way_index.items():
                way_bbox = way_data['bbox']
                south, west, north, east = way_bbox
                
                # Quick bbox check first
                buffer = self.snap_tolerance_m / 111000  # Rough conversion to degrees
                if not (south - buffer <= trace_lat <= north + buffer and
                        west - buffer <= trace_lon <= east + buffer):
                    continue
                
                # Detailed distance check to way coordinates
                way_coords = way_data['coordinates']
                if self._point_near_way(trace_lon, trace_lat, way_coords, self.snap_tolerance_m):
                    matched_ways.add(way_id)
        
        return list(matched_ways)
    
    def _point_near_way(self, 
                       point_lon: float, point_lat: float, 
                       way_coords: List[Dict[str, Any]], 
                       tolerance_m: float) -> bool:
        """Check if point is within tolerance of way coordinates"""
        
        for coord in way_coords:
            way_lon = coord.get('longitude', 0)
            way_lat = coord.get('latitude', 0)
            
            distance_m = self._haversine_m(point_lat, point_lon, way_lat, way_lon)
            if distance_m <= tolerance_m:
                return True
        
        return False
    
    def _update_way_popularity(self, way_ids: List[str], trace: GPXTrace):
        """Update popularity scores for matched ways"""
        
        if not way_ids:
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Calculate trace weight based on recency and activity type
            trace_weight = self._calculate_trace_weight(trace)
            is_motorcycle = trace.activity_type.lower() in ['motorcycle', 'motorbike', 'enduro', 'adv']
            
            for way_id in way_ids:
                # Get existing popularity data
                cursor.execute(
                    'SELECT total_hits, motorcycle_hits, recent_hits, sources FROM way_popularity WHERE way_id = ?',
                    (way_id,)
                )
                result = cursor.fetchone()
                
                if result:
                    total_hits, motorcycle_hits, recent_hits, sources_str = result
                    sources = json.loads(sources_str) if sources_str else []
                else:
                    total_hits, motorcycle_hits, recent_hits = 0, 0, 0
                    sources = []
                
                # Update counters
                total_hits += 1
                if is_motorcycle:
                    motorcycle_hits += 1
                if trace_weight > 0.5:  # Recent trace
                    recent_hits += 1
                
                # Add source if not already present
                if trace.source not in sources:
                    sources.append(trace.source)
                
                # Calculate new popularity score
                popularity_score = self._calculate_popularity_score(
                    total_hits, motorcycle_hits, recent_hits, trace.popularity_signals
                )
                
                # Update or insert
                cursor.execute('''
                    INSERT OR REPLACE INTO way_popularity 
                    (way_id, total_hits, motorcycle_hits, recent_hits, popularity_score, 
                     last_updated, sources)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    way_id, total_hits, motorcycle_hits, recent_hits, 
                    popularity_score, datetime.now(), json.dumps(sources)
                ))
            
            conn.commit()
            conn.close()
            
            self.tracking_stats["ways_updated"] += len(way_ids)
            
        except Exception as e:
            logger.error(f"Failed to update way popularity: {e}")
    
    def _calculate_trace_weight(self, trace: GPXTrace) -> float:
        """Calculate weight for trace based on recency and quality"""
        
        # Age-based decay
        age_years = (datetime.now() - trace.upload_date).days / 365.25
        age_weight = max(0.1, 1.0 - (age_years / self.decay_years))
        
        # Activity type weight
        activity_weight = 1.0
        if trace.activity_type.lower() in ['motorcycle', 'motorbike', 'enduro', 'adv']:
            activity_weight = self.motorcycle_weight
        elif trace.activity_type.lower() in ['bicycle', 'mtb']:
            activity_weight = 0.7  # Some relevance for ADV
        
        # Popularity signals weight
        signals = trace.popularity_signals
        signal_weight = 1.0 + min(0.5, 
            (signals.get('views', 0) / 1000 + 
             signals.get('likes', 0) / 100 + 
             signals.get('downloads', 0) / 50) / 3
        )
        
        return age_weight * activity_weight * signal_weight
    
    def _calculate_popularity_score(self, 
                                  total_hits: int, 
                                  motorcycle_hits: int, 
                                  recent_hits: int,
                                  popularity_signals: Dict[str, float]) -> float:
        """Calculate normalized popularity score (0-1)"""
        
        # Base score from hit counts
        base_score = min(1.0, total_hits / 10.0)  # Normalize to 10 hits = 1.0
        
        # Motorcycle bonus
        moto_ratio = motorcycle_hits / max(1, total_hits)
        moto_bonus = moto_ratio * 0.3
        
        # Recency bonus
        recent_ratio = recent_hits / max(1, total_hits)
        recent_bonus = recent_ratio * 0.2
        
        # External popularity signals
        signals_bonus = min(0.2, 
            (popularity_signals.get('views', 0) / 5000 + 
             popularity_signals.get('likes', 0) / 500) / 2
        )
        
        popularity_score = base_score + moto_bonus + recent_bonus + signals_bonus
        
        return max(0.0, min(1.0, popularity_score))
    
    def _get_cached_popularity(self, way_ids: List[str]) -> Dict[str, WayPopularity]:
        """Get cached popularity data for way IDs"""
        
        if not way_ids:
            return {}
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            placeholders = ','.join('?' * len(way_ids))
            cursor.execute(f'''
                SELECT way_id, coordinates, total_hits, motorcycle_hits, recent_hits,
                       popularity_score, last_updated, sources
                FROM way_popularity 
                WHERE way_id IN ({placeholders})
            ''', way_ids)
            
            results = cursor.fetchall()
            conn.close()
            
            popularity_data = {}
            for row in results:
                way_id, coords_str, total_hits, moto_hits, recent_hits, score, updated_str, sources_str = row
                
                coordinates = json.loads(coords_str) if coords_str else []
                sources = json.loads(sources_str) if sources_str else []
                updated = datetime.fromisoformat(updated_str) if updated_str else datetime.now()
                
                popularity_data[way_id] = WayPopularity(
                    way_id=way_id,
                    coordinates=coordinates,
                    total_hits=total_hits,
                    motorcycle_hits=moto_hits,
                    recent_hits=recent_hits,
                    popularity_score=score,
                    last_updated=updated,
                    sources=sources
                )
                
                self.tracking_stats["cache_hits"] += 1
            
            return popularity_data
            
        except Exception as e:
            logger.error(f"Failed to get cached popularity: {e}")
            return {}
    
    def _store_gpx_trace(self, trace: GPXTrace):
        """Store GPX trace in database for future reference"""
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO gpx_traces
                (trace_id, source, coordinates, activity_type, upload_date, 
                 title, tags, popularity_signals, processed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trace.trace_id,
                trace.source,
                json.dumps(trace.coordinates),
                trace.activity_type,
                trace.upload_date,
                trace.title,
                json.dumps(trace.tags),
                json.dumps(trace.popularity_signals),
                True
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to store GPX trace: {e}")
    
    def _parse_wikiloc_date(self, date_str: str) -> datetime:
        """Parse Wikiloc date string to datetime"""
        
        if not date_str:
            return datetime.now()
            
        try:
            # Try common Wikiloc date formats
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        except Exception as e:
            logger.error(f"Failed to parse Wikiloc date {date_str}: {e}")
        
        return datetime.now()
    
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
    
    def _calculate_popularity_summary(self, 
                                    popularity_data: Dict[str, WayPopularity], 
                                    route_ways: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary statistics for route popularity"""
        
        if not popularity_data:
            return {
                'avg_popularity': 0.0,
                'total_traces': 0,
                'motorcycle_traces': 0,
                'coverage_pct': 0.0
            }
        
        scores = [p.popularity_score for p in popularity_data.values()]
        avg_popularity = sum(scores) / len(scores) if scores else 0.0
        
        total_traces = sum(p.total_hits for p in popularity_data.values())
        motorcycle_traces = sum(p.motorcycle_hits for p in popularity_data.values())
        
        coverage_pct = (len(popularity_data) / len(route_ways)) * 100 if route_ways else 0.0
        
        return {
            'avg_popularity': round(avg_popularity, 2),
            'total_traces': total_traces,
            'motorcycle_traces': motorcycle_traces,
            'coverage_pct': round(coverage_pct, 1)
        }
    
    def _empty_popularity_result(self) -> Dict[str, Any]:
        """Return empty popularity result when no data available"""
        return {
            'way_popularity': {},
            'summary': {
                'avg_popularity': 0.0,
                'total_traces': 0,
                'motorcycle_traces': 0,
                'coverage_pct': 0.0
            },
            'stats': {
                **self.tracking_stats,
                "analysis_time_seconds": 0.0,
                "ways_analyzed": 0,
                "cached_ways": 0
            }
        }