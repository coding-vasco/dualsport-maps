import React, { useState, useEffect } from "react";
import "./App.css";
import axios from "axios";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./components/ui/card";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./components/ui/select";
import { Switch } from "./components/ui/switch";
import { Badge } from "./components/ui/badge";
import { Separator } from "./components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
import { Alert, AlertDescription } from "./components/ui/alert";
import { MapPin, Navigation, Settings, Download, Zap, Mountain, Gauge, Route, Clock, MapIcon, Search, Plus, X, Compass, Camera, TreePine, Fuel } from "lucide-react";
import PlaceSearch from "./components/PlaceSearch";
import RouteMap from "./components/RouteMap";

// Robust backend URL resolver - evaluated at runtime
const getBackendUrl = () => {
  const envUrl = process.env.REACT_APP_BACKEND_URL;
  if (envUrl) {
    return envUrl;
  }
  
  // Runtime hostname detection
  if (typeof window !== 'undefined') {
    if (window.location.hostname === 'localhost' || window.location.port === '3000') {
      return 'http://localhost:8001';
    }
  }
  
  return 'https://dualsport-maps-backend.onrender.com';
};

const BACKEND_URL = getBackendUrl();
const API = `${BACKEND_URL}/api`;

function App() {
  const [routeData, setRouteData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [rateLimitStatus, setRateLimitStatus] = useState(null);
  
  // Route form state
  const [waypoints, setWaypoints] = useState([
    { place: null, coordinates: null, label: "" },
    { place: null, coordinates: null, label: "" }
  ]);
  const [surfacePreference, setSurfacePreference] = useState("mixed");
  const [technicalDifficulty, setTechnicalDifficulty] = useState("moderate");
  const [avoidHighways, setAvoidHighways] = useState(true);
  const [avoidPrimary, setAvoidPrimary] = useState(false);
  const [avoidTrunk, setAvoidTrunk] = useState(true);
  const [outputFormat, setOutputFormat] = useState("geojson");
  const [includeInstructions, setIncludeInstructions] = useState(true);
  const [includeElevation, setIncludeElevation] = useState(true);

  // New enhancement features
  const [useEnhancedRouting, setUseEnhancedRouting] = useState(true);
  const [includePOIs, setIncludePOIs] = useState(true);
  const [includeDirtSegments, setIncludeDirtSegments] = useState(true);
  const [maxDetours, setMaxDetours] = useState(3);
  const [tripDurationHours, setTripDurationHours] = useState("");
  const [tripDistanceKm, setTripDistanceKm] = useState("");
  const [detourRadiusKm, setDetourRadiusKm] = useState(5);
  const [selectedPOITypes, setSelectedPOITypes] = useState(["viewpoint", "fuel", "restaurant"]);

  useEffect(() => {
    fetchRateLimitStatus();
  }, []);

  const fetchRateLimitStatus = async () => {
    try {
      const response = await axios.get(`${API}/rate-limit-status`);
      setRateLimitStatus(response.data);
    } catch (e) {
      console.error("Failed to fetch rate limit status:", e);
    }
  };

  const addWaypoint = () => {
    if (waypoints.length < 50) {
      setWaypoints([...waypoints, { place: null, coordinates: null, label: "" }]);
    }
  };

  const removeWaypoint = (index) => {
    if (waypoints.length > 2) {
      setWaypoints(waypoints.filter((_, i) => i !== index));
    }
  };

  const updateWaypoint = (index, selectedPlace) => {
    const newWaypoints = [...waypoints];
    if (selectedPlace) {
      newWaypoints[index] = {
        place: selectedPlace,
        coordinates: selectedPlace.coordinates,
        label: selectedPlace.label
      };
    } else {
      newWaypoints[index] = { place: null, coordinates: null, label: "" };
    }
    setWaypoints(newWaypoints);
  };

  const togglePOIType = (poiType) => {
    setSelectedPOITypes(prev => 
      prev.includes(poiType) 
        ? prev.filter(type => type !== poiType)
        : [...prev, poiType]
    );
  };

  const calculateRoute = async () => {
    setLoading(true);
    setError("");
    
    try {
      // Validate waypoints
      const validWaypoints = waypoints.filter(wp => 
        wp.coordinates && 
        wp.coordinates.latitude !== undefined && 
        wp.coordinates.longitude !== undefined &&
        !isNaN(wp.coordinates.latitude) && 
        !isNaN(wp.coordinates.longitude)
      );
      
      console.log('Valid waypoints:', validWaypoints);
      
      if (validWaypoints.length < 2) {
        throw new Error("At least 2 valid waypoints are required. Please search and select places for your route.");
      }

      const coordinates = validWaypoints.map(wp => wp.coordinates);
      console.log('Route coordinates:', coordinates);

      let requestData;
      let endpoint;

      if (useEnhancedRouting) {
        // Enhanced route request
        requestData = {
          coordinates,
          surface_preference: surfacePreference,
          technical_difficulty: technicalDifficulty,
          avoid_highways: avoidHighways,
          avoid_primary: avoidPrimary,
          avoid_trunk: avoidTrunk,
          output_format: outputFormat,
          include_instructions: includeInstructions,
          include_elevation: includeElevation,
          poi_types: selectedPOITypes.length > 0 ? selectedPOITypes : ["all"],
          max_detours: maxDetours,
          trip_duration_hours: tripDurationHours ? parseFloat(tripDurationHours) : null,
          trip_distance_km: tripDistanceKm ? parseFloat(tripDistanceKm) : null,
          include_pois: includePOIs,
          include_dirt_segments: includeDirtSegments,
          detour_radius_km: detourRadiusKm
        };
        endpoint = `${API}/route/enhanced`;
      } else {
        // Legacy route request
        requestData = {
          coordinates,
          surface_preference: surfacePreference,
          technical_difficulty: technicalDifficulty,
          avoid_highways: avoidHighways,
          avoid_primary: avoidPrimary,
          avoid_trunk: avoidTrunk,
          output_format: outputFormat,
          include_instructions: includeInstructions,
          include_elevation: includeElevation
        };
        endpoint = `${API}/route`;
      }

      console.log('Sending request to:', endpoint);
      console.log('Request data:', requestData);

      const response = await axios.post(endpoint, requestData, {
        timeout: 60000, // 60 second timeout for enhanced routing
        headers: {
          'Content-Type': 'application/json'
        }
      });

      console.log('Route response received:', response.data);
      setRouteData(response.data);
      await fetchRateLimitStatus();
      
    } catch (e) {
      console.error("Route calculation failed:", e);
      if (e.code === 'ECONNABORTED') {
        setError("Route calculation timed out. This may be due to complex route requirements. Try reducing the number of detours or using legacy routing.");
      } else if (e.response?.status === 429) {
        setError("Rate limit exceeded. Please wait before making another request.");
      } else if (e.response?.status === 422) {
        setError(`Invalid request: ${e.response?.data?.detail || "Please check your route parameters."}`);
      } else if (e.response?.status === 500) {
        setError(`Server error: ${e.response?.data?.detail || "Please try again or use legacy routing."}`);
      } else {
        setError(e.response?.data?.detail || e.message || "Route calculation failed. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const downloadRoute = (format) => {
    if (!routeData) {
      console.error('No route data available for download');
      setError('No route data available for download. Please calculate a route first.');
      return;
    }
    
    try {
      let content, filename, mimeType;
      
      if (format === 'gpx') {
        if (typeof routeData.route === 'string' && routeData.route.includes('<?xml')) {
          // Already GPX format
          content = routeData.route;
        } else {
          // Convert GeoJSON to simple GPX
          content = convertGeoJSONToGPX(routeData.route);
        }
        filename = `dualsport-route-${Date.now()}.gpx`;
        mimeType = 'application/gpx+xml';
      } else {
        // GeoJSON/JSON format
        if (typeof routeData.route === 'string') {
          content = routeData.route;
        } else {
          content = JSON.stringify(routeData.route, null, 2);
        }
        filename = `dualsport-route-${Date.now()}.json`;
        mimeType = 'application/json';
      }
      
      console.log(`Downloading ${format} file:`, { filename, contentLength: content.length });
      
      // Create blob and download
      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      
      // Create download link
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.style.display = 'none';
      
      // Add to DOM, click, and remove
      document.body.appendChild(a);
      a.click();
      
      // Cleanup
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 100);
      
      // Show success message
      console.log(`Successfully downloaded ${filename}`);
      
    } catch (error) {
      console.error('Download failed:', error);
      setError(`Download failed: ${error.message}`);
    }
  };

  const convertGeoJSONToGPX = (geoJsonData) => {
    // Simple GeoJSON to GPX conversion
    const timestamp = new Date().toISOString();
    let gpxContent = `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="DUALSPORT MAPS" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata>
    <name>Dualsport Route</name>
    <desc>Generated by DUALSPORT MAPS</desc>
    <time>${timestamp}</time>
  </metadata>
  <trk>
    <name>Dualsport Route</name>
    <trkseg>`;

    if (geoJsonData && geoJsonData.features && geoJsonData.features[0]) {
      const geometry = geoJsonData.features[0].geometry;
      if (geometry && geometry.type === 'LineString' && geometry.coordinates) {
        geometry.coordinates.forEach(coord => {
          const [lon, lat, ele] = coord;
          gpxContent += `
      <trkpt lat="${lat}" lon="${lon}">`;
          if (ele !== undefined) {
            gpxContent += `
        <ele>${ele}</ele>`;
          }
          gpxContent += `
      </trkpt>`;
        });
      }
    }

    gpxContent += `
    </trkseg>
  </trk>
</gpx>`;

    return gpxContent;
  };

  const formatDistance = (meters) => {
    if (meters < 1000) return `${Math.round(meters)}m`;
    return `${(meters / 1000).toFixed(1)}km`;
  };

  const formatDuration = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  const poiTypeIcons = {
    viewpoint: <Camera className="h-4 w-4" />,
    peak: <Mountain className="h-4 w-4" />,
    fuel: <Fuel className="h-4 w-4" />,
    restaurant: <MapPin className="h-4 w-4" />,
    campsite: <TreePine className="h-4 w-4" />,
    information: <MapIcon className="h-4 w-4" />
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-gray-900 to-slate-800">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="p-3 bg-gradient-to-r from-orange-500 to-red-500 rounded-xl">
              <Compass className="h-8 w-8 text-white" />
            </div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-orange-400 to-red-400 bg-clip-text text-transparent">
              DUALSPORT MAPS
            </h1>
          </div>
          <p className="text-gray-400 text-lg max-w-3xl mx-auto">
            Dualsport route-planning system for adventure motorcycles. Discover scenic backroads, dirt segments, 
            and points of interest perfectly matched to your riding style and bike setup.
          </p>
        </div>

        {/* Rate Limit Status */}
        {rateLimitStatus && (
          <div className="mb-6">
            <Alert className="bg-slate-800 border-slate-700">
              <Zap className="h-4 w-4" />
              <AlertDescription className="text-gray-300">
                API Requests: {rateLimitStatus.requests_remaining} remaining of {rateLimitStatus.daily_limit} daily limit
              </AlertDescription>
            </Alert>
          </div>
        )}

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Route Configuration Panel */}
          <div className="lg:col-span-1 space-y-6">
            <Card className="bg-slate-800 border-slate-700">
              <CardHeader>
                <CardTitle className="text-white flex items-center gap-2">
                  <Settings className="h-5 w-5 text-orange-400" />
                  Route Configuration
                </CardTitle>
                <CardDescription className="text-gray-400">
                  Configure your dualsport route preferences
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Enhanced Routing Toggle */}
                <div className="flex items-center justify-between p-4 bg-gradient-to-r from-orange-900/20 to-red-900/20 rounded-lg border border-orange-400/30">
                  <div>
                    <Label htmlFor="enhanced-routing" className="text-white font-medium">Enhanced Routing</Label>
                    <p className="text-sm text-gray-400">Include POIs and dirt segments</p>
                  </div>
                  <Switch
                    id="enhanced-routing"
                    checked={useEnhancedRouting}
                    onCheckedChange={setUseEnhancedRouting}
                  />
                </div>

                {/* Waypoints */}
                <div>
                  <Label className="text-white mb-3 block flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-orange-400" />
                    Waypoints ({waypoints.length})
                  </Label>
                  <div className="space-y-3">
                    {waypoints.map((waypoint, index) => (
                      <Card key={index} className="bg-slate-700 border-slate-600">
                        <CardContent className="p-4">
                          <div className="flex items-center gap-2 mb-3">
                            <Badge variant="outline" className="border-orange-400 text-orange-400">
                              {index === 0 ? 'Start' : index === waypoints.length - 1 ? 'End' : `Via ${index}`}
                            </Badge>
                            {waypoints.length > 2 && (
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => removeWaypoint(index)}
                                className="text-red-400 hover:text-red-300 p-1 h-6"
                              >
                                <X className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                          <PlaceSearch
                            value={waypoint.place}
                            onChange={(selectedPlace) => updateWaypoint(index, selectedPlace)}
                            placeholder={`Search for ${index === 0 ? 'starting' : index === waypoints.length - 1 ? 'ending' : 'waypoint'} location...`}
                            className="w-full"
                          />
                          {waypoint.coordinates && (
                            <div className="mt-2 text-xs text-gray-400">
                              {waypoint.coordinates.latitude.toFixed(4)}, {waypoint.coordinates.longitude.toFixed(4)}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    ))}
                    {waypoints.length < 50 && (
                      <Button
                        onClick={addWaypoint}
                        variant="outline"
                        className="w-full border-orange-400 text-orange-400 hover:bg-orange-400 hover:text-white"
                      >
                        <Plus className="h-4 w-4 mr-2" />
                        Add Waypoint
                      </Button>
                    )}
                  </div>
                </div>

                <Separator className="bg-slate-600" />

                {/* Enhanced Route Features */}
                {useEnhancedRouting && (
                  <>
                    <div className="space-y-4">
                      <Label className="text-white block">Route Enhancement</Label>
                      
                      {/* Trip Parameters */}
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <Label className="text-gray-300 text-sm">Duration (hours)</Label>
                          <Input
                            type="number"
                            step="0.5"
                            min="1"
                            max="48"
                            value={tripDurationHours}
                            onChange={(e) => setTripDurationHours(e.target.value)}
                            placeholder="8"
                            className="bg-slate-600 border-slate-500 text-white placeholder-gray-400 mt-1"
                          />
                        </div>
                        <div>
                          <Label className="text-gray-300 text-sm">Distance (km)</Label>
                          <Input
                            type="number"
                            min="10"
                            max="2000"
                            value={tripDistanceKm}
                            onChange={(e) => setTripDistanceKm(e.target.value)}
                            placeholder="400"
                            className="bg-slate-600 border-slate-500 text-white placeholder-gray-400 mt-1"
                          />
                        </div>
                      </div>

                      {/* Max Detours */}
                      <div>
                        <Label className="text-gray-300 text-sm">Max Detours: {maxDetours}</Label>
                        <Input
                          type="range"
                          min="0"
                          max="10"
                          value={maxDetours}
                          onChange={(e) => setMaxDetours(parseInt(e.target.value))}
                          className="mt-2"
                        />
                        <div className="flex justify-between text-xs text-gray-400 mt-1">
                          <span>0</span>
                          <span>5</span>
                          <span>10</span>
                        </div>
                      </div>

                      {/* Detour Radius */}
                      <div>
                        <Label className="text-gray-300 text-sm">Detour Radius: {detourRadiusKm}km</Label>
                        <Input
                          type="range"
                          min="1"
                          max="20"
                          value={detourRadiusKm}
                          onChange={(e) => setDetourRadiusKm(parseFloat(e.target.value))}
                          className="mt-2"
                        />
                        <div className="flex justify-between text-xs text-gray-400 mt-1">
                          <span>1km</span>
                          <span>10km</span>
                          <span>20km</span>
                        </div>
                      </div>

                      {/* Enhancement Options */}
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <Label htmlFor="include-pois" className="text-gray-300">Include POIs</Label>
                          <Switch
                            id="include-pois"
                            checked={includePOIs}
                            onCheckedChange={setIncludePOIs}
                          />
                        </div>
                        <div className="flex items-center justify-between">
                          <Label htmlFor="include-dirt" className="text-gray-300">Include Dirt Segments</Label>
                          <Switch
                            id="include-dirt"
                            checked={includeDirtSegments}
                            onCheckedChange={setIncludeDirtSegments}
                          />
                        </div>
                      </div>

                      {/* POI Type Selection */}
                      {includePOIs && (
                        <div>
                          <Label className="text-gray-300 text-sm mb-2 block">Points of Interest</Label>
                          <div className="grid grid-cols-2 gap-2">
                            {[
                              { key: "viewpoint", label: "Viewpoints" },
                              { key: "peak", label: "Peaks" },
                              { key: "fuel", label: "Fuel Stations" },
                              { key: "restaurant", label: "Restaurants" },
                              { key: "campsite", label: "Campsites" },
                              { key: "information", label: "Information" }
                            ].map(poi => (
                              <Button
                                key={poi.key}
                                variant={selectedPOITypes.includes(poi.key) ? "default" : "outline"}
                                size="sm"
                                onClick={() => togglePOIType(poi.key)}
                                className={`text-xs ${
                                  selectedPOITypes.includes(poi.key)
                                    ? "bg-orange-500 hover:bg-orange-600 text-white"
                                    : "border-slate-500 text-gray-300 hover:bg-slate-600"
                                }`}
                              >
                                {poiTypeIcons[poi.key]}
                                <span className="ml-1">{poi.label}</span>
                              </Button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    <Separator className="bg-slate-600" />
                  </>
                )}

                {/* Surface Preference */}
                <div>
                  <Label className="text-white mb-3 block flex items-center gap-2">
                    <Route className="h-4 w-4 text-orange-400" />
                    Surface Preference
                  </Label>
                  <Select value={surfacePreference} onValueChange={setSurfacePreference}>
                    <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-700 border-slate-600">
                      <SelectItem value="paved" className="text-white">Paved Roads</SelectItem>
                      <SelectItem value="mixed" className="text-white">Mixed Surfaces</SelectItem>
                      <SelectItem value="gravel" className="text-white">Gravel Focus</SelectItem>
                      <SelectItem value="dirt" className="text-white">Dirt Tracks</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Technical Difficulty */}
                <div>
                  <Label className="text-white mb-3 block flex items-center gap-2">
                    <Mountain className="h-4 w-4 text-orange-400" />
                    Technical Difficulty
                  </Label>
                  <Select value={technicalDifficulty} onValueChange={setTechnicalDifficulty}>
                    <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-700 border-slate-600">
                      <SelectItem value="easy" className="text-white">Easy</SelectItem>
                      <SelectItem value="moderate" className="text-white">Moderate</SelectItem>
                      <SelectItem value="difficult" className="text-white">Difficult</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Road Type Avoidance */}
                <div className="space-y-4">
                  <Label className="text-white block">Road Type Avoidance</Label>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="avoid-highways" className="text-gray-300">Avoid Highways</Label>
                      <Switch
                        id="avoid-highways"
                        checked={avoidHighways}
                        onCheckedChange={setAvoidHighways}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label htmlFor="avoid-primary" className="text-gray-300">Avoid Primary Roads</Label>
                      <Switch
                        id="avoid-primary"
                        checked={avoidPrimary}
                        onCheckedChange={setAvoidPrimary}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label htmlFor="avoid-trunk" className="text-gray-300">Avoid Trunk Roads</Label>
                      <Switch
                        id="avoid-trunk"
                        checked={avoidTrunk}
                        onCheckedChange={setAvoidTrunk}
                      />
                    </div>
                  </div>
                </div>

                <Separator className="bg-slate-600" />

                {/* Advanced Options */}
                <div className="space-y-4">
                  <Label className="text-white block">Output Options</Label>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="instructions" className="text-gray-300">Include Instructions</Label>
                      <Switch
                        id="instructions"
                        checked={includeInstructions}
                        onCheckedChange={setIncludeInstructions}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label htmlFor="elevation" className="text-gray-300">Include Elevation</Label>
                      <Switch
                        id="elevation"
                        checked={includeElevation}
                        onCheckedChange={setIncludeElevation}
                      />
                    </div>
                  </div>
                </div>

                {/* Output Format */}
                <div>
                  <Label className="text-white mb-3 block">Output Format</Label>
                  <Select value={outputFormat} onValueChange={setOutputFormat}>
                    <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-700 border-slate-600">
                      <SelectItem value="geojson" className="text-white">GeoJSON</SelectItem>
                      <SelectItem value="gpx" className="text-white">GPX</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Calculate Route Button */}
                <Button
                  onClick={calculateRoute}
                  disabled={loading}
                  className="w-full bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white font-semibold py-3"
                >
                  {loading ? (
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      Calculating Route...
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <Compass className="h-4 w-4" />
                      Calculate Dualsport Route
                    </div>
                  )}
                </Button>
              </CardContent>
            </Card>
          </div>

          {/* Results Panel */}
          <div className="lg:col-span-2">
            {error && (
              <Alert className="mb-6 bg-red-900 border-red-700">
                <AlertDescription className="text-red-200">
                  {error}
                </AlertDescription>
              </Alert>
            )}

            {/* Route Map */}
            <div className="mb-6">
              <RouteMap 
                routeData={routeData} 
                waypoints={waypoints}
                className="w-full"
              />
            </div>

            {routeData ? (
              <div className="space-y-6">
                {/* Route Summary */}
                <Card className="bg-slate-800 border-slate-700">
                  <CardHeader>
                    <CardTitle className="text-white flex items-center gap-2">
                      <MapIcon className="h-5 w-5 text-orange-400" />
                      Route Summary
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                      <div className="text-center">
                        <div className="text-2xl font-bold text-orange-400">
                          {formatDistance(routeData.distance)}
                        </div>
                        <div className="text-gray-400 text-sm">Distance</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold text-blue-400 flex items-center justify-center gap-1">
                          <Clock className="h-5 w-5" />
                          {formatDuration(routeData.duration)}
                        </div>
                        <div className="text-gray-400 text-sm">Duration</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold text-green-400">
                          {routeData.elevation_gain ? `${Math.round(routeData.elevation_gain)}m` : 'N/A'}
                        </div>
                        <div className="text-gray-400 text-sm">Elevation Gain</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold text-purple-400">
                          {routeData.waypoint_count}
                        </div>
                        <div className="text-gray-400 text-sm">Waypoints</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Enhanced Route Features */}
                {routeData.enhancements && (
                  <Tabs defaultValue="surface" className="w-full">
                    <TabsList className="grid w-full grid-cols-3 bg-slate-700">
                      <TabsTrigger value="surface" className="data-[state=active]:bg-slate-600">Surface Analysis</TabsTrigger>
                      <TabsTrigger value="pois" className="data-[state=active]:bg-slate-600">POIs ({routeData.enhancements.pois?.length || 0})</TabsTrigger>
                      <TabsTrigger value="dirt" className="data-[state=active]:bg-slate-600">Dirt Segments ({routeData.enhancements.dirt_segments?.length || 0})</TabsTrigger>
                    </TabsList>
                    
                    <TabsContent value="surface" className="mt-4">
                      <Card className="bg-slate-800 border-slate-700">
                        <CardHeader>
                          <CardTitle className="text-white flex items-center gap-2">
                            <Gauge className="h-5 w-5 text-orange-400" />
                            Surface Analysis
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          {routeData.surface_analysis && (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                              {Object.entries(routeData.surface_analysis).map(([surface, percentage]) => (
                                <div key={surface} className="text-center">
                                  <div className="text-xl font-bold text-white">
                                    {Math.round(percentage * 100)}%
                                  </div>
                                  <div className="text-gray-400 text-sm capitalize">{surface}</div>
                                </div>
                              ))}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    </TabsContent>
                    
                    <TabsContent value="pois" className="mt-4">
                      <Card className="bg-slate-800 border-slate-700">
                        <CardHeader>
                          <CardTitle className="text-white flex items-center gap-2">
                            <Camera className="h-5 w-5 text-orange-400" />
                            Points of Interest
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          {routeData.enhancements.pois?.length > 0 ? (
                            <div className="space-y-3">
                              {routeData.enhancements.pois.map((poi, index) => (
                                <div key={poi.id || index} className="flex items-center gap-3 p-3 bg-slate-700 rounded-lg">
                                  <div className="text-orange-400">
                                    {poiTypeIcons[poi.type] || <MapPin className="h-4 w-4" />}
                                  </div>
                                  <div className="flex-1">
                                    <div className="text-white font-medium">{poi.name}</div>
                                    <div className="text-gray-400 text-sm capitalize">{poi.type}</div>
                                  </div>
                                  <div className="text-xs text-gray-500">
                                    {poi.coordinates?.latitude?.toFixed(4)}, {poi.coordinates?.longitude?.toFixed(4)}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="text-gray-400 text-center py-4">
                              No points of interest found along this route.
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    </TabsContent>
                    
                    <TabsContent value="dirt" className="mt-4">
                      <Card className="bg-slate-800 border-slate-700">
                        <CardHeader>
                          <CardTitle className="text-white flex items-center gap-2">
                            <Route className="h-5 w-5 text-orange-400" />
                            Dirt Segments
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          {routeData.enhancements.dirt_segments?.length > 0 ? (
                            <div className="space-y-3">
                              {routeData.enhancements.dirt_segments.map((segment, index) => (
                                <div key={segment.id || index} className="p-3 bg-slate-700 rounded-lg">
                                  <div className="flex items-center justify-between mb-2">
                                    <div className="text-white font-medium">{segment.name}</div>
                                    <Badge variant="outline" className="border-orange-400 text-orange-400 capitalize">
                                      {segment.surface}
                                    </Badge>
                                  </div>
                                  <div className="text-gray-400 text-sm">
                                    Type: {segment.highway} • Track Type: {segment.tracktype}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="text-gray-400 text-center py-4">
                              No dirt segments found along this route.
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    </TabsContent>
                  </Tabs>
                )}

                {/* Download Section */}
                <Card className="bg-slate-800 border-slate-700">
                  <CardHeader>
                    <CardTitle className="text-white flex items-center gap-2">
                      <Download className="h-5 w-5 text-orange-400" />
                      Download Route
                    </CardTitle>
                    <CardDescription className="text-gray-400">
                      Download your route for GPS devices and mapping applications
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex gap-4">
                      <Button
                        onClick={() => downloadRoute('gpx')}
                        variant="outline"
                        className="border-orange-400 text-orange-400 hover:bg-orange-400 hover:text-white"
                      >
                        <Download className="h-4 w-4 mr-2" />
                        Download GPX
                      </Button>
                      <Button
                        onClick={() => downloadRoute('json')}
                        variant="outline"
                        className="border-blue-400 text-blue-400 hover:bg-blue-400 hover:text-white"
                      >
                        <Download className="h-4 w-4 mr-2" />
                        Download GeoJSON
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            ) : (
              <Card className="bg-slate-800 border-slate-700">
                <CardContent className="p-12 text-center">
                  <div className="mb-4">
                    <div className="w-24 h-24 mx-auto bg-gradient-to-r from-orange-500 to-red-500 rounded-full flex items-center justify-center mb-4">
                      <Compass className="h-12 w-12 text-white" />
                    </div>
                  </div>
                  <h3 className="text-xl font-semibold text-white mb-2">
                    Ready to Plan Your Dualsport Adventure?
                  </h3>
                  <p className="text-gray-400 mb-6 max-w-md mx-auto">
                    Search for places, configure your route preferences, and enable enhanced routing 
                    to discover points of interest and dirt segments along your journey.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto text-sm">
                    <div className="bg-slate-700 p-4 rounded-lg">
                      <Search className="h-6 w-6 text-orange-400 mx-auto mb-2" />
                      <div className="text-white font-medium">Place Search</div>
                      <div className="text-gray-400">Type place names with autocomplete suggestions</div>
                    </div>
                    <div className="bg-slate-700 p-4 rounded-lg">
                      <Compass className="h-6 w-6 text-orange-400 mx-auto mb-2" />
                      <div className="text-white font-medium">Enhanced Routing</div>
                      <div className="text-gray-400">Discover POIs and dirt segments</div>
                    </div>
                    <div className="bg-slate-700 p-4 rounded-lg">
                      <Download className="h-6 w-6 text-orange-400 mx-auto mb-2" />
                      <div className="text-white font-medium">Export Options</div>
                      <div className="text-gray-400">GPX for GPS devices, GeoJSON for web apps</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;