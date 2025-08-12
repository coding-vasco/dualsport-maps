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
        
        # Configure highway avoidance based on preferences
        if avoid_highways:
            options["avoid_features"].append("highways")
        if avoid_trunk:
            options["avoid_features"].append("tollways")  # Often includes major trunk roads
            
        return options
    
    def _get_surface_configuration(self, preference: str) -> Dict[str, float]:
        """Configure surface type penalties based on preference"""
        configs = {
            "paved": {
                "asphalt": 1.0,
                "concrete": 1.1,
                "paving_stones": 1.2,
                "gravel": 2.5,
                "dirt": 3.0,
                "grass": 4.0,
                "sand": 5.0
            },
            "mixed": {
                "asphalt": 1.2,
                "concrete": 1.3,
                "gravel": 1.0,
                "compacted": 1.1,
                "dirt": 1.5,
                "grass": 2.5,
                "sand": 3.0
            },
            "gravel": {
                "gravel": 1.0,
                "compacted": 1.1,
                "dirt": 1.3,
                "asphalt": 1.5,
                "concrete": 1.6,
                "grass": 2.0,
                "sand": 3.0
            },
            "dirt": {
                "dirt": 1.0,
                "grass": 1.2,
                "gravel": 1.3,
                "compacted": 1.1,
                "asphalt": 2.0,
                "concrete": 2.1,
                "sand": 2.5
            }
        }
        return configs.get(preference, configs["mixed"])
    
    def _get_difficulty_configuration(self, difficulty: str) -> Dict[str, Any]:
        """Configure routing for different technical difficulty levels"""
        configs = {
            "easy": {
                "weightings": {
                    "steepness_difficulty": 1,
                    "green": 0.3,
                    "quiet": 1.0
                },
                "restrictions": {
                    "gradient": 8,
                    "smoothness": 3  # Limits to good/intermediate surfaces
                }
            },
            "moderate": {
                "weightings": {
                    "steepness_difficulty": 2,
                    "green": 0.5,
                    "quiet": 0.8
                },
                "restrictions": {
                    "gradient": 15,
                    "smoothness": 5  # Allows bad surfaces
                }
            },
            "difficult": {
                "weightings": {
                    "steepness_difficulty": 3,
                    "green": 0.7,
                    "quiet": 0.6
                },
                "restrictions": {
                    "gradient": 25,
                    "smoothness": 7  # Allows very bad surfaces
                }
            }
        }
        return configs.get(difficulty, configs["moderate"])

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
    route: Dict[str, Any]
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
    title="Adventure Motorcycle Route Planner",
    description="ADV route-planning copilot for riders on bikes like the Tenere, Africa Twin, and GS",
    version="1.0.0"
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Global state for rate limiting and client management
ors_client = None
rate_limiter = None

# Helper functions
def convert_to_gpx(route_data: Dict[str, Any], route_name: str = "Adventure Route") -> str:
    """Convert ORS route data to GPX format"""
    
    # Create GPX object
    gpx = gpxpy.gpx.GPX()
    gpx.name = route_name
    gpx.description = "Adventure motorcycle route generated by ORS API"
    gpx.creator = "Adventure Motorcycle Route Planner"
    
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
    optimize_waypoints: bool,
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

async def log_route_request(request: RouteRequest, route_result: Dict[str, Any]):
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

# ADV Route Planning Endpoints
@api_router.post("/route", response_model=RouteResponse)
async def calculate_route(
    request: RouteRequest,
    background_tasks: BackgroundTasks
):
    """Calculate adventure motorcycle route with custom preferences"""
    
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
            optimize_waypoints=request.optimize_waypoints,
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
    return {"message": "Adventure Motorcycle Route Planner API"}

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
    format='%(asctime)s - %(name)s - %(levelevel)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    global ors_client, rate_limiter
    if OPENROUTE_API_KEY:
        ors_client = AdvancedORS(OPENROUTE_API_KEY)
        rate_limiter = RateLimiter()
        logger.info("OpenRouteService client initialized")
    else:
        logger.error("OPENROUTE_API_KEY not found in environment variables")

@app.on_event("shutdown")
async def shutdown_event():
    if ors_client:
        await ors_client.close()
    client.close()