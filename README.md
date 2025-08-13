# DUALSPORT MAPS

Adventure motorcycle route planning system with intelligent dirt road discovery, elevation analysis, and scenic route optimization.

## 🏍️ Features

- **Intelligent Route Planning**: Advanced algorithms for ADV-focused routing
- **Dirt Road Discovery**: Comprehensive OSM and Overpass API integration
- **Elevation Analysis**: DEM-based grade computation and ridge preference
- **Imagery Validation**: Street-level imagery verification via Mapillary
- **Community Insights**: Popularity tracking from Wikiloc and other sources
- **Multiple Route Options**: Various difficulty levels and surface preferences

## 🚀 Deployment on Render

### Prerequisites

1. **MongoDB Atlas Account**: Create a free cluster at [MongoDB Atlas](https://cloud.mongodb.com/)
2. **API Tokens**: Obtain tokens for external services (optional, features degrade gracefully):
   - OpenRouteService API Key (required)
   - Mapbox Token (for elevation analysis)
   - Mapillary Token (for imagery validation)
   - Wikiloc integration (web scraping based)
   - Strava API Token (for segment data)

### Quick Deploy

1. **Fork this repository** to your GitHub account

2. **Create a new Web Service** on Render:
   - Connect your GitHub repository
   - Use the `render.yaml` blueprint (auto-detected)
   - Set your environment variables

3. **Required Environment Variables**:
   ```
   MONGO_URL=mongodb+srv://username:password@cluster.mongodb.net/dualsport_maps_prod
   OPENROUTE_API_KEY=your_openroute_api_key
   ```

4. **Optional Environment Variables** (features enable automatically):
   ```
   MAPBOX_TOKEN=your_mapbox_token
   MAPILLARY_TOKEN=your_mapillary_token
   STRAVA_TOKEN=your_strava_token
   ```

### Manual Deployment Steps

1. **Database Setup**:
   - Create MongoDB Atlas cluster
   - Get connection string
   - Add to Render environment variables as `MONGO_URL`

2. **API Keys Setup**:
   - OpenRouteService: Required for basic routing
   - Mapbox: Enables elevation analysis and DEM features
   - Mapillary: Enables imagery validation
   - Strava: Enables popularity tracking from segments

3. **Deploy**:
   - Connect GitHub repository to Render
   - Backend deploys as Web Service
   - Frontend deploys as Static Site
   - Environment variables auto-configure CORS and API endpoints

## 🔧 Local Development

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8001
```

### Frontend Setup
```bash
cd frontend
yarn install
yarn start
```

### Environment Variables (.env files)
Create `.env` files in both `backend/` and `frontend/` directories with your API keys.

## 📊 API Endpoints

### Basic Routing
- `POST /api/route` - Legacy route calculation
- `POST /api/route/enhanced` - Enhanced route with POIs and dirt segments
- `POST /api/route/advanced` - Advanced route with comprehensive analysis

### Utilities
- `POST /api/places/search` - Place name geocoding
- `GET /api/rate-limit-status` - Current API usage status

### Response Features
- Multiple route options with confidence scores
- Comprehensive diagnostics and analysis
- GPX and GeoJSON export formats
- Evidence-based routing decisions

## 🏗️ Architecture

- **Backend**: FastAPI with async processing
- **Frontend**: React with Leaflet mapping
- **Database**: MongoDB for caching and analytics
- **External APIs**: OpenRouteService, Mapbox, Mapillary, Wikiloc
- **Deployment**: Render with separate backend/frontend services

## 📈 Scaling

- **Frontend**: Static site with CDN distribution (scales automatically)
- **Backend**: Horizontal scaling available on Render
- **Database**: MongoDB Atlas handles automatic scaling
- **Caching**: In-memory and database caching for external API calls

## 🔒 Security

- Environment variables for all API keys
- CORS properly configured for production
- Rate limiting on all endpoints
- Input validation and sanitization

## 📝 License

Private project - All rights reserved.

## 🤝 Contributing

This is a private project. For questions or suggestions, please contact the maintainer.

---

**Happy trail riding! 🏍️🌲**