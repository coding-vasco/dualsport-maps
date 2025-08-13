# 🚀 DUALSPORT MAPS - Render Deployment Guide

## 📋 Pre-Deployment Checklist

### 1. GitHub Repository Setup
- [ ] Create new GitHub repository
- [ ] Upload this code to the repository
- [ ] Ensure `render.yaml` is in the root directory

### 2. Database Setup (MongoDB Atlas)
- [ ] Create free MongoDB Atlas account at https://cloud.mongodb.com/
- [ ] Create a new cluster (M0 Sandbox - Free tier)
- [ ] Create database user with read/write permissions
- [ ] Get connection string (format: `mongodb+srv://username:password@cluster.mongodb.net/`)
- [ ] Whitelist IP addresses (0.0.0.0/0 for Render access)

### 3. API Tokens Collection

#### Required (Basic Functionality)
- **OpenRouteService**: Already configured
  - Value: `eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImVkZjk5NDA5MGViMjRiMzg5OThjNDc3ZWFiNzRjNTI3IiwiaCI6Im11cm11cjY0In0=`

#### Optional (Enhanced Features)
- **Mapbox**: ✅ Already configured
  - Value: `pk.eyJ1IjoidmFzY29mZXJuYW5kZXMiLCJhIjoiY21lOTZ6MTIxMG8wZzJrcXZjamk2dmtmMyJ9.T4vl8y8v_gbfhKLNiEt-hA`
  - Enables: Elevation analysis, ridge detection, DEM features

- **Strava API**: ⏳ Setup needed
  - Go to: https://developers.strava.com/
  - Create new app with these settings:
    - **Website**: `https://your-app-name.onrender.com` (get from Render after deployment)
    - **Authorization Callback Domain**: `your-app-name.onrender.com`
  - Get Client ID and Client Secret
  - Enables: Segment popularity data, heat maps

- **Mapillary API**: ⏳ Setup needed
  - Go to: https://www.mapillary.com/developer
  - Create new app with these settings:
    - **Website**: `https://your-app-name.onrender.com`
    - **Redirect URL**: `https://your-app-name.onrender.com/auth/mapillary/callback`
  - Get Access Token
  - Enables: Street-level imagery validation, gate/barrier detection

## 🏗️ Render Deployment Steps

### Step 1: Create Backend Service
1. Go to Render Dashboard → "New" → "Web Service"
2. Connect your GitHub repository
3. Configure:
   - **Name**: `dualsport-maps-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `cd backend && pip install -r requirements.txt`
   - **Start Command**: `cd backend && python start.py`
   - **Plan**: `Starter` (can upgrade later)

### Step 2: Set Backend Environment Variables
Add these in Render Backend service settings:

```
MONGO_URL=mongodb+srv://username:password@cluster.mongodb.net/dualsport_maps_prod
DB_NAME=dualsport_maps_prod
OPENROUTE_API_KEY=eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImVkZjk5NDA5MGViMjRiMzg5OThjNDc3ZWFiNzRjNTI3IiwiaCI6Im11cm11cjY0In0=
MAPBOX_TOKEN=pk.eyJ1IjoidmFzY29mZXJuYW5kZXMiLCJhIjoiY21lOTZ6MTIxMG8wZzJrcXZjamk2dmtmMyJ9.T4vl8y8v_gbfhKLNiEt-hA
CORS_ORIGINS=*
```

### Step 3: Create Frontend Service
1. Go to Render Dashboard → "New" → "Static Site"
2. Connect same GitHub repository
3. Configure:
   - **Name**: `dualsport-maps-frontend`
   - **Build Command**: `cd frontend && yarn install && yarn build`
   - **Publish Directory**: `frontend/build`

### Step 4: Set Frontend Environment Variable
Add this in Render Frontend service settings:
```
REACT_APP_BACKEND_URL=https://dualsport-maps-backend.onrender.com
```
(Replace with your actual backend URL from Step 1)

### Step 5: Deploy
- Both services will automatically deploy
- Frontend will be available at: `https://dualsport-maps-frontend.onrender.com`
- Backend will be available at: `https://dualsport-maps-backend.onrender.com`

## 🔧 Post-Deployment Setup

### 1. Get Your URLs
After deployment, note your URLs:
- **Frontend**: `https://your-frontend-name.onrender.com`
- **Backend**: `https://your-backend-name.onrender.com`

### 2. Complete API Setups
Now that you have production URLs, complete the API setups:

#### Strava API
- Update your Strava app settings with the production URL
- Add the Client Secret to Render environment variables:
  ```
  STRAVA_TOKEN=your_strava_client_secret
  ```

#### Mapillary API  
- Update your Mapillary app settings with the production URL
- Add the Access Token to Render environment variables:
  ```
  MAPILLARY_TOKEN=your_mapillary_access_token
  ```

### 3. Test Deployment
- Visit your frontend URL
- Test basic route planning functionality
- Check that advanced features work with enabled tokens

## 💰 Cost Optimization

### Free Tier Resources
- **Frontend**: Static Site (Free - unlimited)
- **Backend**: Starter Plan ($7/month after free tier expires)
- **Database**: MongoDB Atlas M0 (Free - 512MB)

### Scaling Path
1. **Start**: Free static frontend + Starter backend + Free MongoDB
2. **Growth**: Upgrade backend to Standard ($25/month)
3. **Scale**: Add multiple backend instances, upgrade MongoDB cluster

## 🔍 Monitoring & Debugging

### Render Logs
- Backend logs: Available in Render Dashboard → Service → Logs
- Monitor for errors, API rate limits, performance issues

### Health Checks
- Backend health: `https://your-backend.onrender.com/api/`
- Database connectivity: Check MongoDB Atlas metrics

### Performance
- Target: < 8s median response time for route planning
- Monitor via Render metrics dashboard

## 🚨 Troubleshooting

### Common Issues
1. **502 Bad Gateway**: Backend not starting - check logs for Python errors
2. **CORS Issues**: Verify CORS_ORIGINS environment variable
3. **Database Connection**: Check MongoDB Atlas IP whitelist and credentials
4. **API Rate Limits**: Monitor external API usage in logs

### Support
- Render Support: Available in dashboard
- MongoDB Atlas Support: Available in their console
- GitHub Issues: For code-specific problems

---

## 📞 Next Steps After Deployment

1. **Share your production URLs** so we can complete API integrations
2. **Test the deployment** with a few route planning requests
3. **Proceed with Phase 2 implementation** (core modules and new features)

**Ready to deploy!** 🎉