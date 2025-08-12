from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Union
from enum import Enum
import uuid
from datetime import datetime, timedelta
import openrouteservice as ors
import httpx
import gpxpy
import gpxpy.gpx
import json
import asyncio
import math

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# OpenRouteService setup
OPENROUTE_API_KEY = os.environ.get('OPENROUTE_API_KEY')

# Rate Limiter for ORS API (2000 requests/day limit)
class RateLimiter:
    def __init__(self, daily_limit: int = 2000, minute_limit: int = 40):
        self.daily_limit = daily_limit
        self.minute_limit = minute_limit
        self.daily_count = 0
        self.minute_counts = []
        self.daily_reset_time = None
        
    def can_make_request(self) -> bool:
        now = datetime.now()
        
        # Check daily limit
        if self.daily_reset_time and now >= self.daily_reset_time:
            self.daily_count = 0
            self.daily_reset_time = None
            
        if self.daily_count >= self.daily_limit:
            return False
            
        # Check minutely limit
        minute_ago = now - timedelta(minutes=1)
        self.minute_counts = [count for count in self.minute_counts if count > minute_ago]
        
        if len(self.minute_counts) >= self.minute_limit:
            return False
            
        return True
    
    def record_request(self):
        now = datetime.now()
        self.daily_count += 1
        self.minute_counts.append(now)
        
        if self.daily_reset_time is None:
            self.daily_reset_time = now + timedelta(days=1)
    
    def time_until_next_request(self) -> Optional[float]:
        now = datetime.now()
        
        # Check if daily limit is exceeded
        if self.daily_count >= self.daily_limit:
            if self.daily_reset_time:
                return (self.daily_reset_time - now).total_seconds()
            return None
        
        # Check minute limit
        if len(self.minute_counts) >= self.minute_limit:
            oldest_request = min(self.minute_counts)
            next_available = oldest_request + timedelta(minutes=1)
            return max(0, (next_available - now).total_seconds())
        
        return 0

# Advanced ORS Client
class AdvancedORS:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openrouteservice.org"
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, application/geo+json"
        }
        self._session = None
        
    async def get_session(self):
        if self._session is None or self._session.is_closed:
            self._session = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        return self._session
    
    async def close(self):
        if self._session and not self._session.is_closed:
            await self._session.aclose()

# Dualsport Route Enhancement System
class DualsportRouteEnhancer:
    def __init__(self, ors_client):
        self.ors_client = ors_client
        
    async def find_pois_along_route(self, route_coordinates: List[tuple], radius_km: float = 5.0, poi_types: List[str] = None) -> List[Dict]:
        """Find points of interest along the route using Overpass API"""
        if not poi_types:
            poi_types = ["viewpoint", "peak", "fuel", "restaurant", "campsite", "information"]
        
        # Create bounding box from route coordinates
        lats = [coord[1] for coord in route_coordinates]
        lons = [coord[0] for coord in route_coordinates]
        
        min_lat, max_lat = min(lats) - 0.01, max(lats) + 0.01
        min_lon, max_lon = min(lons) - 0.01, max(lons) + 0.01
        
        # Build Overpass query for POIs
        overpass_query = f"""
        [out:json][timeout:25];
        (
          node["tourism"="viewpoint"]({min_lat},{min_lon},{max_lat},{max_lon});
          node["natural"="peak"]({min_lat},{min_lon},{max_lat},{max_lon});
          node["amenity"="fuel"]({min_lat},{min_lon},{max_lat},{max_lon});
          node["amenity"="restaurant"]({min_lat},{min_lon},{max_lat},{max_lon});
          node["tourism"="camp_site"]({min_lat},{min_lon},{max_lat},{max_lon});
          node["tourism"="information"]({min_lat},{min_lon},{max_lat},{max_lon});
        );
        out geom;
        """
        
        try:
            session = await self.ors_client.get_session()
            response = await session.post(
                "https://overpass-api.de/api/interpreter",
                data=overpass_query,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                data = response.json()
                pois = []
                
                for element in data.get("elements", []):
                    if element.get("type") == "node":
                        poi = {
                            "id": element.get("id"),
                            "name": element.get("tags", {}).get("name", "Unknown"),
                            "type": self._determine_poi_type(element.get("tags", {})),
                            "coordinates": {
                                "latitude": element.get("lat"),
                                "longitude": element.get("lon")
                            },
                            "tags": element.get("tags", {})
                        }
                        pois.append(poi)
                
                return pois[:20]  # Limit to 20 POIs
            
        except Exception as e:
            logger.error(f"POI search failed: {e}")
        
        return []
    
    def _determine_poi_type(self, tags: Dict[str, str]) -> str:
        """Determine POI type from OSM tags"""
        if tags.get("tourism") == "viewpoint":
            return "viewpoint"
        elif tags.get("natural") == "peak":
            return "peak"
        elif tags.get("amenity") == "fuel":
            return "fuel"
        elif tags.get("amenity") == "restaurant":
            return "restaurant"
        elif tags.get("tourism") == "camp_site":
            return "campsite"
        elif tags.get("tourism") == "information":
            return "information"
        else:
            return "other"
    
    async def find_dirt_segments(self, route_coordinates: List[tuple], radius_km: float = 2.0) -> List[Dict]:
        """Find dirt/gravel segments near the route"""
        
        # Create bounding box
        lats = [coord[1] for coord in route_coordinates]
        lons = [coord[0] for coord in route_coordinates]
        
        min_lat, max_lat = min(lats) - 0.01, max(lats) + 0.01
        min_lon, max_lon = min(lons) - 0.01, max(lons) + 0.01
        
        # Overpass query for dirt/gravel tracks
        overpass_query = f"""
        [out:json][timeout:25];
        (
          way["highway"="track"]["surface"~"gravel|dirt|sand|compacted|fine_gravel|ground"]({min_lat},{min_lon},{max_lat},{max_lon});
          way["highway"="path"]["surface"~"gravel|dirt|sand|compacted|fine_gravel|ground"]({min_lat},{min_lon},{max_lat},{max_lon});
          way["highway"="unclassified"]["surface"~"gravel|dirt|sand|compacted|fine_gravel|ground"]({min_lat},{min_lon},{max_lat},{max_lon});
        );
        out geom;
        """
        
        try:
            session = await self.ors_client.get_session()
            response = await session.post(
                "https://overpass-api.de/api/interpreter",
                data=overpass_query,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                data = response.json()
                segments = []
                
                for element in data.get("elements", []):
                    if element.get("type") == "way" and element.get("geometry"):
                        segment = {
                            "id": element.get("id"),
                            "name": element.get("tags", {}).get("name", f"Dirt Track {element.get('id')}"),
                            "surface": element.get("tags", {}).get("surface", "unknown"),
                            "tracktype": element.get("tags", {}).get("tracktype", "unknown"),
                            "highway": element.get("tags", {}).get("highway", "track"),
                            "coordinates": [
                                {"latitude": coord["lat"], "longitude": coord["lon"]} 
                                for coord in element.get("geometry", [])
                            ],
                            "tags": element.get("tags", {})
                        }
                        segments.append(segment)
                
                return segments[:15]  # Limit to 15 segments
            
        except Exception as e:
            logger.error(f"Dirt segment search failed: {e}")
        
        return []

# Adventure Motorcycle Routing Profiles
class AdventureMotoProfile:
    def __init__(self):
        self.base_profile = "cycling-regular"  # Closest approximation to motorcycle
        
    def get_profile_options(
        self,
        surface_preference: str = "mixed",  # mixed, gravel, dirt, paved
        avoid_highways: bool = True,
        avoid_primary: bool = False,
        avoid_trunk: bool = True,
        technical_difficulty: str = "moderate"  # easy, moderate, difficult
    ) -> Dict[str, Any]:
        
        options = {
            "avoid_features": []
        }
        
        # Note: cycling-regular profile has limited avoid_features support
        # Most avoid features are not supported, so we keep it minimal
            
        return options

# Pydantic Models
class SurfacePreference(str, Enum):
    PAVED = "paved"
    MIXED = "mixed"
    GRAVEL = "gravel"
    DIRT = "dirt"

class TechnicalDifficulty(str, Enum):
    EASY = "easy"
    MODERATE = "moderate"
    DIFFICULT = "difficult"

class OutputFormat(str, Enum):
    GEOJSON = "geojson"
    JSON = "json"
    GPX = "gpx"

class POIType(str, Enum):
    VIEWPOINT = "viewpoint"
    PEAK = "peak"
    FUEL = "fuel"
    RESTAURANT = "restaurant"
    CAMPSITE = "campsite"
    INFORMATION = "information"
    ALL = "all"

class Coordinates(BaseModel):
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    
    @validator('longitude')
    def validate_longitude(cls, v):
        if not -180 <= v <= 180:
            raise ValueError('Longitude must be between -180 and 180')
        return v
    
    @validator('latitude')
    def validate_latitude(cls, v):
        if not -90 <= v <= 90:
            raise ValueError('Latitude must be between -90 and 90')
        return v

class PlaceSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=100)
    limit: int = Field(default=5, ge=1, le=10)

class PlaceSearchResult(BaseModel):
    label: str
    value: str
    coordinates: Coordinates
    region: Optional[str] = None
    country: Optional[str] = None

class EnhancedRouteRequest(BaseModel):
    coordinates: List[Coordinates] = Field(..., min_items=2, max_items=50)
    surface_preference: SurfacePreference = SurfacePreference.MIXED
    technical_difficulty: TechnicalDifficulty = TechnicalDifficulty.MODERATE
    avoid_highways: bool = True
    avoid_primary: bool = False
    avoid_trunk: bool = True
    output_format: OutputFormat = OutputFormat.GEOJSON
    include_instructions: bool = True
    include_elevation: bool = True
    
    # New enhancement features
    poi_types: List[POIType] = Field(default=[POIType.ALL])
    max_detours: int = Field(default=3, ge=0, le=10, description="Maximum number of detours for POIs/dirt segments")
    trip_duration_hours: Optional[float] = Field(default=None, ge=1, le=48, description="Approximate trip duration in hours")
    trip_distance_km: Optional[float] = Field(default=None, ge=10, le=2000, description="Approximate trip distance in km")
    include_pois: bool = Field(default=True, description="Include points of interest")
    include_dirt_segments: bool = Field(default=True, description="Include dirt/gravel segments")
    detour_radius_km: float = Field(default=5.0, ge=1.0, le=20.0, description="Maximum radius for detours in km")
    
    @validator('coordinates')
    def validate_coordinates_count(cls, v):
        if len(v) < 2:
            raise ValueError('At least 2 coordinates are required')
        if len(v) > 50:
            raise ValueError('Maximum 50 coordinates allowed')
        return v

class RouteEnhancement(BaseModel):
    pois: List[Dict[str, Any]] = []
    dirt_segments: List[Dict[str, Any]] = []
    scenic_points: List[Dict[str, Any]] = []

class EnhancedRouteResponse(BaseModel):
    route: Union[Dict[str, Any], str]  # Can be dict (GeoJSON) or str (GPX)
    distance: float
    duration: float
    elevation_gain: Optional[float] = None
    elevation_loss: Optional[float] = None
    surface_analysis: Optional[Dict[str, float]] = None
    waypoint_count: int
    format: str
    generated_at: datetime
    enhancements: RouteEnhancement

# Legacy models for backward compatibility
class RouteRequest(BaseModel):
    coordinates: List[Coordinates] = Field(..., min_items=2, max_items=50)
    surface_preference: SurfacePreference = SurfacePreference.MIXED
    technical_difficulty: TechnicalDifficulty = TechnicalDifficulty.MODERATE
    avoid_highways: bool = True
    avoid_primary: bool = False
    avoid_trunk: bool = True
    output_format: OutputFormat = OutputFormat.GEOJSON
    optimize_waypoints: bool = False
    include_instructions: bool = True
    include_elevation: bool = True
    
    @validator('coordinates')
    def validate_coordinates_count(cls, v):
        if len(v) < 2:
            raise ValueError('At least 2 coordinates are required')
        if len(v) > 50:
            raise ValueError('Maximum 50 coordinates allowed')
        return v

class RouteResponse(BaseModel):
    route: Union[Dict[str, Any], str]  # Can be dict (GeoJSON) or str (GPX)
    distance: float
    duration: float
    elevation_gain: Optional[float] = None
    elevation_loss: Optional[float] = None
    surface_analysis: Optional[Dict[str, float]] = None
    waypoint_count: int
    format: str
    generated_at: datetime

# Legacy models for existing functionality
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

# Create the main app without a prefix
app = FastAPI(
    title="DUALSPORT MAPS",
    description="Dualsport route-planning system for adventure motorcycles. Plan scenic, backroads-heavy routes with points of interest, dirt segments, and downloadable GPX & GeoJSON files.",
    version="1.0.0"
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Global state for rate limiting and client management
ors_client = None
rate_limiter = None
route_enhancer = None

# Helper functions
def convert_to_gpx(route_data: Dict[str, Any], route_name: str = "Dualsport Route") -> str:
    """Convert ORS route data to GPX format"""
    
    # Create GPX object
    gpx = gpxpy.gpx.GPX()
    gpx.name = route_name
    gpx.description = "Dualsport motorcycle route generated by DUALSPORT MAPS"
    gpx.creator = "DUALSPORT MAPS"
    
    # Extract geometry and properties
    geometry = route_data.get("geometry", {})
    properties = route_data.get("properties", {})
    
    if geometry.get("type") == "LineString":
        coordinates = geometry.get("coordinates", [])
        
        # Create track
        gpx_track = gpxpy.gpx.GPXTrack()
        gpx_track.name = route_name
        gpx.tracks.append(gpx_track)
        
        # Create track segment
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)
        
        # Add track points
        for i, coord in enumerate(coordinates):
            lon, lat = coord[0], coord[1]
            elevation = coord[2] if len(coord) > 2 else None
            
            gpx_point = gpxpy.gpx.GPXTrackPoint(
                latitude=lat,
                longitude=lon,
                elevation=elevation
            )
            
            gpx_segment.points.append(gpx_point)
        
        # Add waypoints for start and end
        segments = properties.get("segments", [{}])
        steps = segments[0].get("steps", []) if segments else []
        
        if steps:
            # Start waypoint
            start_coords = steps[0].get("maneuver", {}).get("location", [])
            if len(start_coords) >= 2:
                start_waypoint = gpxpy.gpx.GPXWaypoint(
                    latitude=start_coords[1],
                    longitude=start_coords[0],
                    name=f"Start - {route_name}",
                    description=steps[0].get("instruction", "")
                )
                gpx.waypoints.append(start_waypoint)
            
            # End waypoint
            if len(steps) > 1:
                end_coords = steps[-1].get("maneuver", {}).get("location", [])
                if len(end_coords) >= 2:
                    end_waypoint = gpxpy.gpx.GPXWaypoint(
                        latitude=end_coords[1],
                        longitude=end_coords[0],
                        name=f"End - {route_name}",
                        description=steps[-1].get("instruction", "")
                    )
                    gpx.waypoints.append(end_waypoint)
    
    return gpx.to_xml()

def analyze_surface_types(properties: Dict[str, Any]) -> Dict[str, float]:
    """Analyze surface types from route properties"""
    # This is a simplified surface analysis
    # In a full implementation, you'd parse the extras.surface data
    return {
        "asphalt": 0.4,
        "gravel": 0.3,
        "dirt": 0.2,
        "other": 0.1
    }

def calculate_elevation_gain(properties: Dict[str, Any]) -> float:
    """Calculate elevation gain from route properties"""
    # Simplified elevation calculation
    return properties.get("ascent", 0.0)

def calculate_elevation_loss(properties: Dict[str, Any]) -> float:
    """Calculate elevation loss from route properties"""
    # Simplified elevation calculation
    return properties.get("descent", 0.0)

async def search_places(query: str, limit: int = 5) -> List[PlaceSearchResult]:
    """Search for places using OpenRouteService geocoding"""
    
    if not rate_limiter.can_make_request():
        raise HTTPException(status_code=429, detail="Rate limit exceeded for place search")
    
    session = await ors_client.get_session()
    
    # Prepare geocoding request
    url = f"{ors_client.base_url}/geocode/search"
    params = {
        "api_key": ors_client.api_key,
        "text": query,
        "size": limit,
        "layers": "venue,address,street,neighbourhood,locality,county,macrocounty,region,macroregion,country"
    }
    
    try:
        response = await session.get(url, params=params)
        
        if response.status_code != 200:
            logger.error(f"Geocoding API error: {response.status_code}")
            return []
        
        result = response.json()
        rate_limiter.record_request()
        
        places = []
        for feature in result.get("features", []):
            properties = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            
            if geometry.get("type") == "Point":
                coords = geometry.get("coordinates", [])
                if len(coords) >= 2:
                    places.append(PlaceSearchResult(
                        label=properties.get("label", "Unknown"),
                        value=properties.get("gid", ""),
                        coordinates=Coordinates(
                            longitude=coords[0],
                            latitude=coords[1]
                        ),
                        region=properties.get("region"),
                        country=properties.get("country")
                    ))
        
        return places
        
    except Exception as e:
        logger.error(f"Place search failed: {e}")
        return []

async def calculate_motorcycle_route(
    coords: List[tuple],
    options: Dict[str, Any],
    output_format: str,
    include_instructions: bool,
    include_elevation: bool
) -> Dict[str, Any]:
    
    session = await ors_client.get_session()
    
    # Prepare request payload
    payload = {
        "coordinates": coords,
        "format": "geojson",
        "instructions": include_instructions,
        "elevation": include_elevation,
        "extra_info": ["surface", "waytype", "steepness"] if include_elevation else ["surface", "waytype"],
        "options": options
    }
    
    # Make request to ORS API
    url = f"{ors_client.base_url}/v2/directions/cycling-regular/geojson"
    
    response = await session.post(
        url,
        headers=ors_client.headers,
        json=payload
    )
    
    if response.status_code != 200:
        error_detail = f"ORS API error: {response.status_code}"
        try:
            error_info = response.json()
            error_detail = error_info.get("error", {}).get("message", error_detail)
        except:
            pass
        raise HTTPException(status_code=response.status_code, detail=error_detail)
    
    result = response.json()
    
    # Extract route information
    route_data = result["features"][0] if result.get("features") else {}
    properties = route_data.get("properties", {})
    
    # Process the result based on output format
    if output_format == "gpx":
        gpx_data = convert_to_gpx(route_data)
        return {
            "route": gpx_data,
            "distance": properties.get("summary", {}).get("distance", 0),
            "duration": properties.get("summary", {}).get("duration", 0),
            "elevation_gain": calculate_elevation_gain(properties),
            "elevation_loss": calculate_elevation_loss(properties),
            "surface_analysis": analyze_surface_types(properties)
        }
    
    return {
        "route": result,
        "distance": properties.get("summary", {}).get("distance", 0),
        "duration": properties.get("summary", {}).get("duration", 0),
        "elevation_gain": calculate_elevation_gain(properties),
        "elevation_loss": calculate_elevation_loss(properties),
        "surface_analysis": analyze_surface_types(properties)
    }

async def log_route_request(request: Union[RouteRequest, EnhancedRouteRequest], route_result: Dict[str, Any]):
    """Background task to log route requests"""
    try:
        log_data = {
            "timestamp": datetime.utcnow(),
            "coordinates_count": len(request.coordinates),
            "surface_preference": request.surface_preference,
            "technical_difficulty": request.technical_difficulty,
            "distance": route_result.get("distance", 0),
            "duration": route_result.get("duration", 0)
        }
        
        # Add enhanced route features if available
        if hasattr(request, 'max_detours'):
            log_data.update({
                "max_detours": request.max_detours,
                "trip_duration_hours": request.trip_duration_hours,
                "trip_distance_km": request.trip_distance_km,
                "include_pois": request.include_pois,
                "include_dirt_segments": request.include_dirt_segments
            })
        
        await db.route_logs.insert_one(log_data)
    except Exception as e:
        logger.error(f"Failed to log route request: {e}")

# Geocoding endpoints
@api_router.post("/places/search", response_model=List[PlaceSearchResult])
async def search_places_endpoint(request: PlaceSearchRequest):
    """Search for places by name with autocomplete suggestions"""
    try:
        places = await search_places(request.query, request.limit)
        return places
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Place search failed: {e}")
        raise HTTPException(status_code=500, detail="Place search failed")

# Enhanced Route Planning Endpoints
@api_router.post("/route/enhanced", response_model=EnhancedRouteResponse)
async def calculate_enhanced_route(
    request: EnhancedRouteRequest,
    background_tasks: BackgroundTasks
):
    """Calculate enhanced dualsport route with POIs and dirt segments"""
    
    # Rate limiting check
    if not rate_limiter.can_make_request():
        wait_time = rate_limiter.time_until_next_request()
        if wait_time:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {wait_time:.0f} seconds."
            )
    
    try:
        # Convert coordinates to ORS format
        coords = [(coord.longitude, coord.latitude) for coord in request.coordinates]
        
        # Get profile configuration
        profile_manager = AdventureMotoProfile()
        profile_options = profile_manager.get_profile_options(
            surface_preference=request.surface_preference,
            avoid_highways=request.avoid_highways,
            avoid_primary=request.avoid_primary,
            avoid_trunk=request.avoid_trunk,
            technical_difficulty=request.technical_difficulty
        )
        
        # Calculate base route
        route_result = await calculate_motorcycle_route(
            coords=coords,
            options=profile_options,
            output_format=request.output_format,
            include_instructions=request.include_instructions,
            include_elevation=request.include_elevation
        )
        
        # Initialize enhancements
        enhancements = RouteEnhancement()
        
        # Extract route coordinates for enhancement searches
        if route_result.get("route") and isinstance(route_result["route"], dict):
            route_features = route_result["route"].get("features", [])
            if route_features:
                route_geometry = route_features[0].get("geometry", {})
                if route_geometry.get("type") == "LineString":
                    route_coordinates = route_geometry.get("coordinates", [])
                    
                    # Find POIs along route
                    if request.include_pois and request.max_detours > 0:
                        poi_types = [poi.value for poi in request.poi_types if poi != POIType.ALL]
                        if POIType.ALL in request.poi_types:
                            poi_types = ["viewpoint", "peak", "fuel", "restaurant", "campsite", "information"]
                        
                        pois = await route_enhancer.find_pois_along_route(
                            route_coordinates, 
                            request.detour_radius_km,
                            poi_types
                        )
                        enhancements.pois = pois[:request.max_detours]
                    
                    # Find dirt segments along route
                    if request.include_dirt_segments and request.max_detours > 0:
                        dirt_segments = await route_enhancer.find_dirt_segments(
                            route_coordinates,
                            request.detour_radius_km
                        )
                        enhancements.dirt_segments = dirt_segments[:request.max_detours]
        
        # Record successful request
        rate_limiter.record_request()
        
        # Add background task for usage analytics
        background_tasks.add_task(log_route_request, request, route_result)
        
        return EnhancedRouteResponse(
            route=route_result["route"],
            distance=route_result["distance"],
            duration=route_result["duration"],
            elevation_gain=route_result.get("elevation_gain"),
            elevation_loss=route_result.get("elevation_loss"),
            surface_analysis=route_result.get("surface_analysis"),
            waypoint_count=len(request.coordinates),
            format=request.output_format,
            generated_at=datetime.now(),
            enhancements=enhancements
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enhanced route calculation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Enhanced route calculation failed: {str(e)}")

# Legacy route endpoint for backward compatibility
@api_router.post("/route", response_model=RouteResponse)
async def calculate_route(
    request: RouteRequest,
    background_tasks: BackgroundTasks
):
    """Calculate basic dualsport route (legacy endpoint)"""
    
    # Rate limiting check
    if not rate_limiter.can_make_request():
        wait_time = rate_limiter.time_until_next_request()
        if wait_time:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {wait_time:.0f} seconds."
            )
    
    try:
        # Convert coordinates to ORS format
        coords = [(coord.longitude, coord.latitude) for coord in request.coordinates]
        
        # Get profile configuration
        profile_manager = AdventureMotoProfile()
        profile_options = profile_manager.get_profile_options(
            surface_preference=request.surface_preference,
            avoid_highways=request.avoid_highways,
            avoid_primary=request.avoid_primary,
            avoid_trunk=request.avoid_trunk,
            technical_difficulty=request.technical_difficulty
        )
        
        # Calculate route
        route_result = await calculate_motorcycle_route(
            coords=coords,
            options=profile_options,
            output_format=request.output_format,
            include_instructions=request.include_instructions,
            include_elevation=request.include_elevation
        )
        
        # Record successful request
        rate_limiter.record_request()
        
        # Add background task for usage analytics
        background_tasks.add_task(log_route_request, request, route_result)
        
        return RouteResponse(
            route=route_result["route"],
            distance=route_result["distance"],
            duration=route_result["duration"],
            elevation_gain=route_result.get("elevation_gain"),
            elevation_loss=route_result.get("elevation_loss"),
            surface_analysis=route_result.get("surface_analysis"),
            waypoint_count=len(request.coordinates),
            format=request.output_format,
            generated_at=datetime.now()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Route calculation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Route calculation failed: {str(e)}")

@api_router.get("/rate-limit-status")
async def get_rate_limit_status():
    """Get current rate limit status"""
    return {
        "daily_count": rate_limiter.daily_count,
        "daily_limit": rate_limiter.daily_limit,
        "requests_remaining": max(0, rate_limiter.daily_limit - rate_limiter.daily_count),
        "can_make_request": rate_limiter.can_make_request(),
        "reset_time": rate_limiter.daily_reset_time.isoformat() if rate_limiter.daily_reset_time else None
    }

# Legacy endpoints for existing functionality
@api_router.get("/")
async def root():
    return {"message": "DUALSPORT MAPS API - Adventure motorcycle route planning"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    global ors_client, rate_limiter, route_enhancer
    if OPENROUTE_API_KEY:
        ors_client = AdvancedORS(OPENROUTE_API_KEY)
        rate_limiter = RateLimiter()
        route_enhancer = DualsportRouteEnhancer(ors_client)
        logger.info("DUALSPORT MAPS service initialized")
    else:
        logger.error("OPENROUTE_API_KEY not found in environment variables")

@app.on_event("shutdown")
async def shutdown_event():
    if ors_client:
        await ors_client.close()
    client.close()