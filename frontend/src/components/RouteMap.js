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

// Custom icons for waypoints
const createCustomIcon = (color, text, size = 32) => {
  return L.divIcon({
    className: 'custom-div-icon',
    html: `
      <div style="
        background-color: ${color};
        width: ${size}px;
        height: ${size}px;
        border-radius: 50%;
        border: 3px solid white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        color: white;
        font-size: ${Math.floor(size * 0.35)}px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      ">${text}</div>
    `,
    iconSize: [size, size],
    iconAnchor: [size/2, size/2],
  });
};

// Custom icons for POIs
const createPOIIcon = (type, color = '#f97316') => {
  const icons = {
    viewpoint: '📷',
    peak: '⛰️',
    fuel: '⛽',
    restaurant: '🍽️',
    campsite: '🏕️',
    information: 'ℹ️',
    other: '📍'
  };
  
  const emoji = icons[type] || icons.other;
  
  return L.divIcon({
    className: 'poi-div-icon',
    html: `
      <div style="
        background-color: ${color};
        width: 28px;
        height: 28px;
        border-radius: 50%;
        border: 2px solid white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        position: relative;
      ">
        <div style="filter: drop-shadow(0 1px 1px rgba(0,0,0,0.3));">${emoji}</div>
        <div style="
          position: absolute;
          bottom: -2px;
          right: -2px;
          width: 8px;
          height: 8px;
          background-color: #16a34a;
          border: 1px solid white;
          border-radius: 50%;
        "></div>
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
};

// Custom icons for dirt segments
const createDirtIcon = (surface) => {
  const colors = {
    gravel: '#8b5a00',
    dirt: '#92400e',
    sand: '#fbbf24',
    compacted: '#6b7280',
    default: '#78716c'
  };
  
  const color = colors[surface] || colors.default;
  
  return L.divIcon({
    className: 'dirt-div-icon',
    html: `
      <div style="
        background-color: ${color};
        width: 20px;
        height: 20px;
        border-radius: 3px;
        border: 2px solid white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        color: white;
        font-size: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
      ">🏍️</div>
    `,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
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
        <p className="text-gray-400">Calculate a route to see the map visualization with POIs and dirt segments</p>
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
  const waypointMarkers = waypoints
    .filter(wp => wp.coordinates && wp.coordinates.latitude && wp.coordinates.longitude)
    .map((wp, index) => ({
      position: [wp.coordinates.latitude, wp.coordinates.longitude],
      label: wp.label || `Waypoint ${index + 1}`,
      isStart: index === 0,
      isEnd: index === waypoints.length - 1,
    }));

  // Process POIs for markers
  const poiMarkers = routeData.enhancements?.pois?.map((poi, index) => ({
    position: [poi.coordinates.latitude, poi.coordinates.longitude],
    name: poi.name,
    type: poi.type,
    description: `${poi.type.charAt(0).toUpperCase() + poi.type.slice(1)} • ${poi.name}`
  })) || [];

  // Process dirt segments for markers
  const dirtMarkers = routeData.enhancements?.dirt_segments?.slice(0, 5).map((segment, index) => {
    // Use first coordinate of the segment
    const firstCoord = segment.coordinates?.[0];
    if (!firstCoord) return null;
    
    return {
      position: [firstCoord.latitude, firstCoord.longitude],
      name: segment.name,
      surface: segment.surface,
      description: `${segment.surface.charAt(0).toUpperCase() + segment.surface.slice(1)} Track • ${segment.name}`
    };
  }).filter(Boolean) || [];

  const center = routeCoordinates.length > 0 
    ? routeCoordinates[Math.floor(routeCoordinates.length / 2)]
    : [39.8283, -98.5795]; // Center of US as fallback

  return (
    <div className={`bg-slate-800 border border-slate-700 rounded-lg overflow-hidden ${className}`}>
      <div className="p-4 border-b border-slate-700">
        <h3 className="text-lg font-semibold text-white mb-1">Route Preview</h3>
        <p className="text-gray-400 text-sm">
          Interactive map showing your dualsport route with POIs and dirt segments
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
          
          {/* Route line with enhanced styling */}
          {routeCoordinates.length > 0 && (
            <Polyline
              positions={routeCoordinates}
              pathOptions={{
                color: '#f97316',
                weight: 5,
                opacity: 0.9,
                lineCap: 'round',
                lineJoin: 'round',
                dashArray: '0, 10'
              }}
            />
          )}
          
          {/* Waypoint markers */}
          {waypointMarkers.map((marker, index) => (
            <Marker
              key={`waypoint-${index}`}
              position={marker.position}
              icon={marker.isStart ? startIcon : marker.isEnd ? endIcon : waypointIcon}
            >
              <Popup>
                <div className="text-sm">
                  <div className="font-semibold text-gray-800">
                    {marker.isStart ? '🚩 Start' : marker.isEnd ? '🏁 End' : `📍 Waypoint ${index}`}
                  </div>
                  <div className="text-gray-600 mt-1">{marker.label}</div>
                  <div className="text-xs text-gray-500 mt-1">
                    {marker.position[0].toFixed(4)}, {marker.position[1].toFixed(4)}
                  </div>
                </div>
              </Popup>
            </Marker>
          ))}
          
          {/* POI markers */}
          {poiMarkers.map((poi, index) => (
            <Marker
              key={`poi-${index}`}
              position={poi.position}
              icon={createPOIIcon(poi.type, '#3b82f6')}
            >
              <Popup>
                <div className="text-sm">
                  <div className="font-semibold text-gray-800">
                    📍 {poi.name}
                  </div>
                  <div className="text-gray-600 mt-1 capitalize">{poi.type}</div>
                  <div className="text-xs text-gray-500 mt-1">
                    Point of Interest
                  </div>
                </div>
              </Popup>
            </Marker>
          ))}
          
          {/* Dirt segment markers */}
          {dirtMarkers.map((dirt, index) => (
            <Marker
              key={`dirt-${index}`}
              position={dirt.position}
              icon={createDirtIcon(dirt.surface)}
            >
              <Popup>
                <div className="text-sm">
                  <div className="font-semibold text-gray-800">
                    🏍️ {dirt.name}
                  </div>
                  <div className="text-gray-600 mt-1 capitalize">{dirt.surface} Surface</div>
                  <div className="text-xs text-gray-500 mt-1">
                    Dirt Segment
                  </div>
                </div>
              </Popup>
            </Marker>
          ))}
          
          {/* Fit bounds to route and markers */}
          {bounds.length > 0 && <FitBounds bounds={bounds} />}
        </MapContainer>
      </div>
      
      {/* Enhanced legend */}
      <div className="p-4 bg-slate-700 border-t border-slate-600">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-green-500 rounded-full"></div>
            <span className="text-gray-300">Start</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-orange-500 rounded-full"></div>
            <span className="text-gray-300">Route</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
            <span className="text-gray-300">POIs ({poiMarkers.length})</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-amber-600 rounded-full"></div>
            <span className="text-gray-300">Dirt ({dirtMarkers.length})</span>
          </div>
        </div>
        <div className="text-xs text-gray-400 mt-2">
          {routeCoordinates.length} route points • Click markers for details
        </div>
      </div>
    </div>
  );
};

export default RouteMap;