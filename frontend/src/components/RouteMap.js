import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix for default markers in React Leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

// Custom icons for start and end points
const createCustomIcon = (color, text) => {
  return L.divIcon({
    className: 'custom-div-icon',
    html: `
      <div style="
        background-color: ${color};
        width: 32px;
        height: 32px;
        border-radius: 50%;
        border: 3px solid white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        color: white;
        font-size: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      ">${text}</div>
    `,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
};

const startIcon = createCustomIcon('#16a34a', 'S');
const endIcon = createCustomIcon('#dc2626', 'E');
const waypointIcon = createCustomIcon('#f97316', 'W');

// Component to fit map bounds to route
const FitBounds = ({ bounds }) => {
  const map = useMap();
  
  useEffect(() => {
    if (bounds && bounds.length > 0) {
      map.fitBounds(bounds, { padding: [20, 20] });
    }
  }, [map, bounds]);
  
  return null;
};

const RouteMap = ({ routeData, waypoints = [], className = "" }) => {
  const mapRef = useRef(null);

  if (!routeData) {
    return (
      <div className={`bg-slate-800 border border-slate-700 rounded-lg p-8 text-center ${className}`}>
        <div className="text-gray-400 mb-4">
          <svg className="w-16 h-16 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-1.447-.894L15 4m0 13V4m0 0L9 7" />
          </svg>
        </div>
        <h3 className="text-lg font-semibold text-white mb-2">Route Preview</h3>
        <p className="text-gray-400">Calculate a route to see the map visualization</p>
      </div>
    );
  }

  // Extract route coordinates
  let routeCoordinates = [];
  let bounds = [];
  
  try {
    if (routeData.route && routeData.route.features && routeData.route.features[0]) {
      const geometry = routeData.route.features[0].geometry;
      if (geometry && geometry.type === 'LineString') {
        routeCoordinates = geometry.coordinates.map(coord => [coord[1], coord[0]]); // [lat, lng]
        bounds = routeCoordinates;
      }
    }
  } catch (error) {
    console.error('Error parsing route data:', error);
  }

  // Process waypoints for markers
  const markers = waypoints
    .filter(wp => wp.coordinates && wp.coordinates.latitude && wp.coordinates.longitude)
    .map((wp, index) => ({
      position: [wp.coordinates.latitude, wp.coordinates.longitude],
      label: wp.label || `Waypoint ${index + 1}`,
      isStart: index === 0,
      isEnd: index === waypoints.length - 1,
    }));

  const center = routeCoordinates.length > 0 
    ? routeCoordinates[Math.floor(routeCoordinates.length / 2)]
    : [39.8283, -98.5795]; // Center of US as fallback

  return (
    <div className={`bg-slate-800 border border-slate-700 rounded-lg overflow-hidden ${className}`}>
      <div className="p-4 border-b border-slate-700">
        <h3 className="text-lg font-semibold text-white mb-1">Route Preview</h3>
        <p className="text-gray-400 text-sm">
          Interactive map showing your adventure motorcycle route
        </p>
      </div>
      
      <div className="relative" style={{ height: '400px' }}>
        <MapContainer
          ref={mapRef}
          center={center}
          zoom={10}
          style={{ height: '100%', width: '100%' }}
          scrollWheelZoom={true}
          zoomControl={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          
          {/* Route line */}
          {routeCoordinates.length > 0 && (
            <Polyline
              positions={routeCoordinates}
              pathOptions={{
                color: '#f97316',
                weight: 4,
                opacity: 0.8,
                lineCap: 'round',
                lineJoin: 'round'
              }}
            />
          )}
          
          {/* Waypoint markers */}
          {markers.map((marker, index) => (
            <Marker
              key={index}
              position={marker.position}
              icon={marker.isStart ? startIcon : marker.isEnd ? endIcon : waypointIcon}
            >
              <Popup>
                <div className="text-sm">
                  <div className="font-semibold">
                    {marker.isStart ? 'Start' : marker.isEnd ? 'End' : `Waypoint ${index}`}
                  </div>
                  <div className="text-gray-600">{marker.label}</div>
                  <div className="text-xs text-gray-500 mt-1">
                    {marker.position[0].toFixed(4)}, {marker.position[1].toFixed(4)}
                  </div>
                </div>
              </Popup>
            </Marker>
          ))}
          
          {/* Fit bounds to route */}
          {bounds.length > 0 && <FitBounds bounds={bounds} />}
        </MapContainer>
      </div>
      
      {routeCoordinates.length > 0 && (
        <div className="p-4 bg-slate-700 border-t border-slate-600">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                <span className="text-gray-300">Start</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-orange-500 rounded-full"></div>
                <span className="text-gray-300">Route</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-red-500 rounded-full"></div>
                <span className="text-gray-300">End</span>
              </div>
            </div>
            <div className="text-gray-400">
              {routeCoordinates.length} route points
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RouteMap;