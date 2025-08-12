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
import { MapPin, Navigation, Settings, Download, Zap, Mountain, Gauge, Route, Clock, MapIcon } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [routeData, setRouteData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [rateLimitStatus, setRateLimitStatus] = useState(null);
  
  // Route form state
  const [waypoints, setWaypoints] = useState([
    { latitude: "", longitude: "" },
    { latitude: "", longitude: "" }
  ]);
  const [surfacePreference, setSurfacePreference] = useState("mixed");
  const [technicalDifficulty, setTechnicalDifficulty] = useState("moderate");
  const [avoidHighways, setAvoidHighways] = useState(true);
  const [avoidPrimary, setAvoidPrimary] = useState(false);
  const [avoidTrunk, setAvoidTrunk] = useState(true);
  const [outputFormat, setOutputFormat] = useState("geojson");
  const [optimizeWaypoints, setOptimizeWaypoints] = useState(false);
  const [includeInstructions, setIncludeInstructions] = useState(true);
  const [includeElevation, setIncludeElevation] = useState(true);

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
      setWaypoints([...waypoints, { latitude: "", longitude: "" }]);
    }
  };

  const removeWaypoint = (index) => {
    if (waypoints.length > 2) {
      setWaypoints(waypoints.filter((_, i) => i !== index));
    }
  };

  const updateWaypoint = (index, field, value) => {
    const newWaypoints = [...waypoints];
    newWaypoints[index][field] = value;
    setWaypoints(newWaypoints);
  };

  const calculateRoute = async () => {
    setLoading(true);
    setError("");
    
    try {
      // Validate waypoints
      const validWaypoints = waypoints.filter(wp => 
        wp.latitude !== "" && wp.longitude !== "" && 
        !isNaN(parseFloat(wp.latitude)) && !isNaN(parseFloat(wp.longitude))
      );
      
      if (validWaypoints.length < 2) {
        throw new Error("At least 2 valid waypoints are required");
      }

      const coordinates = validWaypoints.map(wp => ({
        latitude: parseFloat(wp.latitude),
        longitude: parseFloat(wp.longitude)
      }));

      const requestData = {
        coordinates,
        surface_preference: surfacePreference,
        technical_difficulty: technicalDifficulty,
        avoid_highways: avoidHighways,
        avoid_primary: avoidPrimary,
        avoid_trunk: avoidTrunk,
        output_format: outputFormat,
        optimize_waypoints: optimizeWaypoints,
        include_instructions: includeInstructions,
        include_elevation: includeElevation
      };

      const response = await axios.post(`${API}/route`, requestData);
      setRouteData(response.data);
      await fetchRateLimitStatus();
      
    } catch (e) {
      console.error("Route calculation failed:", e);
      if (e.response?.status === 429) {
        setError("Rate limit exceeded. Please wait before making another request.");
      } else {
        setError(e.response?.data?.detail || e.message || "Route calculation failed");
      }
    } finally {
      setLoading(false);
    }
  };

  const downloadRoute = (format) => {
    if (!routeData) return;
    
    let content, filename, mimeType;
    
    if (format === 'gpx') {
      content = routeData.route;
      filename = `adv-route-${Date.now()}.gpx`;
      mimeType = 'application/gpx+xml';
    } else {
      content = JSON.stringify(routeData.route, null, 2);
      filename = `adv-route-${Date.now()}.json`;
      mimeType = 'application/json';
    }
    
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-gray-900 to-slate-800">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="p-3 bg-gradient-to-r from-orange-500 to-red-500 rounded-xl">
              <Navigation className="h-8 w-8 text-white" />
            </div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-orange-400 to-red-400 bg-clip-text text-transparent">
              ADV Route Planner
            </h1>
          </div>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">
            Adventure route-planning copilot for riders on bikes like the Tenere, Africa Twin, and GS. 
            Plan scenic, backroads-heavy, dirt-friendly routes with downloadable GPX & GeoJSON.
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
          <div className="lg:col-span-1">
            <Card className="bg-slate-800 border-slate-700">
              <CardHeader>
                <CardTitle className="text-white flex items-center gap-2">
                  <Settings className="h-5 w-5 text-orange-400" />
                  Route Configuration
                </CardTitle>
                <CardDescription className="text-gray-400">
                  Configure your adventure motorcycle route preferences
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
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
                          <div className="flex items-center gap-2 mb-2">
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
                                ×
                              </Button>
                            )}
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <Input
                              type="number"
                              step="any"
                              placeholder="Latitude"
                              value={waypoint.latitude}
                              onChange={(e) => updateWaypoint(index, 'latitude', e.target.value)}
                              className="bg-slate-600 border-slate-500 text-white placeholder-gray-400"
                            />
                            <Input
                              type="number"
                              step="any"
                              placeholder="Longitude"
                              value={waypoint.longitude}
                              onChange={(e) => updateWaypoint(index, 'longitude', e.target.value)}
                              className="bg-slate-600 border-slate-500 text-white placeholder-gray-400"
                            />
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                    {waypoints.length < 50 && (
                      <Button
                        onClick={addWaypoint}
                        variant="outline"
                        className="w-full border-orange-400 text-orange-400 hover:bg-orange-400 hover:text-white"
                      >
                        Add Waypoint
                      </Button>
                    )}
                  </div>
                </div>

                <Separator className="bg-slate-600" />

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
                  <Label className="text-white block">Advanced Options</Label>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="optimize" className="text-gray-300">Optimize Waypoints</Label>
                      <Switch
                        id="optimize"
                        checked={optimizeWaypoints}
                        onCheckedChange={setOptimizeWaypoints}
                      />
                    </div>
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
                      <Navigation className="h-4 w-4" />
                      Calculate ADV Route
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

                {/* Surface Analysis */}
                {routeData.surface_analysis && (
                  <Card className="bg-slate-800 border-slate-700">
                    <CardHeader>
                      <CardTitle className="text-white flex items-center gap-2">
                        <Gauge className="h-5 w-5 text-orange-400" />
                        Surface Analysis
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
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
                    </CardContent>
                  </Card>
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
                        Download JSON
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
                      <Navigation className="h-12 w-12 text-white" />
                    </div>
                  </div>
                  <h3 className="text-xl font-semibold text-white mb-2">
                    Ready to Plan Your Adventure?
                  </h3>
                  <p className="text-gray-400 mb-6 max-w-md mx-auto">
                    Configure your route preferences and waypoints on the left, then hit "Calculate ADV Route" 
                    to generate your adventure motorcycle route with downloadable GPX and GeoJSON files.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto text-sm">
                    <div className="bg-slate-700 p-4 rounded-lg">
                      <Route className="h-6 w-6 text-orange-400 mx-auto mb-2" />
                      <div className="text-white font-medium">Surface Preferences</div>
                      <div className="text-gray-400">Choose from paved, mixed, gravel, or dirt focus</div>
                    </div>
                    <div className="bg-slate-700 p-4 rounded-lg">
                      <Mountain className="h-6 w-6 text-orange-400 mx-auto mb-2" />
                      <div className="text-white font-medium">Technical Difficulty</div>
                      <div className="text-gray-400">Easy, moderate, or difficult terrain</div>
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