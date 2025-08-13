"""
Phase 2 Integration Module
Integrates the new Phase 2 core modules with existing Phase 1 infrastructure.

Provides a unified interface for:
- Segment feature extraction
- Custom model building  
- Detour optimization
- Enhanced route planning workflow
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from .segment_features import SegmentFeatureExtractor, SegmentFeature
from .custom_model_builder import CustomModelBuilder, RouteWeights, AdvVariant, ModelConfiguration
from .detour_optimizer import DetourOptimizer, DetourConstraints, DetourOptimizationResult
from .route_planner_enhanced import EnhancedRoutePlanner, RoutePlanRequest, RouteOption

logger = logging.getLogger(__name__)

@dataclass
class Phase2Configuration:
    """Configuration for Phase 2 enhanced routing"""
    enable_segment_features: bool = True
    enable_custom_models: bool = True  
    enable_detour_optimization: bool = True
    
    # Feature extraction settings
    feature_extraction_budget: float = 8.0
    curvature_analysis: bool = True
    elevation_analysis: bool = True
    environmental_analysis: bool = True
    
    # Model building settings
    auto_select_variant: bool = True
    default_variant: AdvVariant = AdvVariant.ADV_MIXED
    
    # Detour optimization settings
    detour_optimization_budget: float = 12.0
    max_detours: int = 3
    detour_radius_km: float = 5.0
    min_detour_gain: float = 0.05

class Phase2EnhancedPlanner:
    """Enhanced route planner integrating all Phase 2 capabilities"""
    
    def __init__(self,
                 base_planner: EnhancedRoutePlanner,
                 dem_analyzer=None,
                 imagery_validator=None,
                 popularity_tracker=None,
                 overpass_client=None):
        
        self.base_planner = base_planner
        
        # Initialize Phase 2 modules
        self.segment_extractor = SegmentFeatureExtractor(
            dem_analyzer=dem_analyzer,
            imagery_validator=imagery_validator,
            popularity_tracker=popularity_tracker
        )
        
        self.model_builder = CustomModelBuilder()
        
        self.detour_optimizer = DetourOptimizer(
            segment_extractor=self.segment_extractor,
            route_planner=base_planner,
            overpass_client=overpass_client
        )
        
        self.integration_stats = {
            "enhanced_routes_planned": 0,
            "segment_features_extracted": 0,
            "custom_models_built": 0,
            "detours_optimized": 0,
            "phase2_errors": 0
        }

    async def plan_enhanced_routes_v2(self,
                                    request: RoutePlanRequest,
                                    config: Phase2Configuration = None) -> Dict[str, Any]:
        """
        Plan routes using Phase 2 enhanced capabilities
        
        Workflow:
        1. Generate baseline routes using Phase 1 system
        2. Extract segment features for route analysis
        3. Build custom routing models based on user preferences
        4. Apply detour optimization for scenic/dirt enhancement
        5. Return enhanced routes with comprehensive analytics
        """
        
        start_time = time.time()
        config = config or Phase2Configuration()
        
        logger.info(f"Planning enhanced routes v2 with Phase 2 capabilities")
        
        try:
            # Step 1: Generate baseline routes using existing Phase 1 system
            baseline_result = await self.base_planner.plan_enhanced_routes(request)
            
            if not baseline_result['route_options']:
                logger.warning("No baseline routes generated, returning Phase 1 result")
                return baseline_result
            
            # Step 2: Extract segment features if enabled
            segment_features = []
            if config.enable_segment_features:
                segment_features = await self._extract_route_segment_features(
                    baseline_result['route_options'],
                    config.feature_extraction_budget
                )
            
            # Step 3: Build custom routing models if enabled
            custom_models = {}
            if config.enable_custom_models:
                route_weights = self._convert_request_to_weights(request)
                custom_models = await self._build_custom_models(
                    route_weights, segment_features, config
                )
            
            # Step 4: Apply detour optimization if enabled
            optimized_routes = []
            if config.enable_detour_optimization and segment_features:
                optimized_routes = await self._optimize_routes_with_detours(
                    baseline_result['route_options'],
                    request,
                    segment_features,
                    config
                )
            else:
                optimized_routes = baseline_result['route_options']
            
            # Step 5: Enhance route options with Phase 2 data
            enhanced_options = await self._enhance_route_options(
                optimized_routes,
                segment_features,
                custom_models,
                config
            )
            
            # Step 6: Build comprehensive result
            phase2_result = await self._build_phase2_result(
                baseline_result,
                enhanced_options,
                segment_features,
                custom_models,
                start_time,
                config
            )
            
            self.integration_stats["enhanced_routes_planned"] += 1
            
            elapsed = time.time() - start_time
            logger.info(f"Phase 2 enhanced planning completed in {elapsed:.2f}s")
            
            return phase2_result
            
        except Exception as e:
            logger.error(f"Phase 2 enhanced planning failed: {e}")
            self.integration_stats["phase2_errors"] += 1
            
            # Fallback to Phase 1 result
            return baseline_result if 'baseline_result' in locals() else {
                'route_options': [],
                'diagnostics': {'phase2_error': str(e)},
                'stats': {'phase2_enabled': False}
            }

    async def _extract_route_segment_features(self,
                                            route_options: List[RouteOption],
                                            budget: float) -> List[List[SegmentFeature]]:
        """Extract segment features for all route options"""
        
        all_features = []
        per_route_budget = budget / len(route_options) if route_options else 0
        
        for i, route_option in enumerate(route_options):
            try:
                # Convert route to segments
                segments = self._route_to_segments(route_option)
                
                # Extract features
                features = await self.segment_extractor.extract_segment_features(
                    segments, per_route_budget
                )
                
                all_features.append(features)
                self.integration_stats["segment_features_extracted"] += len(features)
                
            except Exception as e:
                logger.error(f"Feature extraction failed for route {i}: {e}")
                all_features.append([])
        
        return all_features

    def _route_to_segments(self, route_option: RouteOption) -> List[Dict[str, Any]]:
        """Convert RouteOption to segments for feature extraction"""
        
        segments = []
        
        # Extract coordinates from route geometry
        if hasattr(route_option, 'route_data') and route_option.route_data:
            route_data = route_option.route_data
            
            if isinstance(route_data, dict) and 'geometry' in route_data:
                geometry = route_data['geometry']
                
                if isinstance(geometry, dict) and 'coordinates' in geometry:
                    coords = geometry['coordinates']
                    
                    # Split into segments (every ~1km for analysis)
                    segment_coords = self._split_coordinates_into_segments(coords, target_length_km=1.0)
                    
                    for i, seg_coords in enumerate(segment_coords):
                        segment = {
                            'segment_id': f"{route_option.route_id}_seg_{i}",
                            'coordinates': [
                                {'longitude': c[0], 'latitude': c[1]} 
                                for c in seg_coords
                            ],
                            'tags': {}  # Would extract from route properties if available
                        }
                        segments.append(segment)
        
        return segments

    def _split_coordinates_into_segments(self,
                                       coordinates: List[List[float]],
                                       target_length_km: float = 1.0) -> List[List[Tuple[float, float]]]:
        """Split coordinate list into segments of approximately target length"""
        
        if len(coordinates) < 2:
            return []
        
        segments = []
        current_segment = []
        current_length = 0.0
        
        for i, coord in enumerate(coordinates):
            current_segment.append((coord[0], coord[1]))
            
            if i > 0:
                prev_coord = coordinates[i-1]
                segment_distance = self._haversine_km(
                    prev_coord[1], prev_coord[0], coord[1], coord[0]
                )
                current_length += segment_distance
            
            # Start new segment when target length reached
            if current_length >= target_length_km and len(current_segment) >= 2:
                segments.append(current_segment.copy())
                current_segment = [current_segment[-1]]  # Overlap last point
                current_length = 0.0
        
        # Add final segment if it has content
        if len(current_segment) >= 2:
            segments.append(current_segment)
        
        return segments

    def _convert_request_to_weights(self, request: RoutePlanRequest) -> RouteWeights:
        """Convert RoutePlanRequest to RouteWeights for custom model building"""
        
        # Extract weights from request (Phase 2 request format)
        weights_data = getattr(request, 'weights', {})
        
        return RouteWeights(
            dirt=weights_data.get('dirt', 0.6),
            scenic=weights_data.get('scenic', 0.4),
            risk=weights_data.get('risk', -0.2),
            popularity=weights_data.get('popularity', 0.2),
            prefer_surfaces=getattr(request, 'prefer_surfaces', None),
            avoid_surfaces=getattr(request, 'avoid_surfaces', None),
            minimize_classes=getattr(request, 'minimize_classes', None),
            avoid_steep_over_pct=getattr(request, 'avoid_steep_over_pct', 14.0),
            off_pavement_target_pct=getattr(request, 'off_pavement_target_pct', 60.0)
        )

    async def _build_custom_models(self,
                                 route_weights: RouteWeights,
                                 segment_features: List[List[SegmentFeature]],
                                 config: Phase2Configuration) -> Dict[AdvVariant, ModelConfiguration]:
        """Build custom routing models for the request"""
        
        try:
            # Flatten segment features for model building
            all_features = []
            for route_features in segment_features:
                all_features.extend(route_features)
            
            # Determine variants to build
            if config.auto_select_variant:
                # Select variants based on user preferences
                variants = self._select_optimal_variants(route_weights)
            else:
                variants = [config.default_variant]
            
            # Build models
            models = self.model_builder.build_variant_models(
                route_weights, variants, all_features
            )
            
            self.integration_stats["custom_models_built"] += len(models)
            
            return models
            
        except Exception as e:
            logger.error(f"Custom model building failed: {e}")
            return {}

    def _select_optimal_variants(self, weights: RouteWeights) -> List[AdvVariant]:
        """Select optimal ADV variants based on user weights"""
        
        variants = []
        
        # Conservative riders (low risk tolerance, moderate dirt preference)
        if weights.risk < -0.4 or weights.dirt < 0.4:
            variants.append(AdvVariant.ADV_EASY)
        
        # Always include mixed for comparison
        variants.append(AdvVariant.ADV_MIXED)
        
        # Aggressive riders (high dirt preference, risk tolerant)
        if weights.dirt > 0.7 or weights.risk > -0.1:
            variants.append(AdvVariant.ADV_TECH)
        
        return list(set(variants))  # Remove duplicates

    async def _optimize_routes_with_detours(self,
                                          route_options: List[RouteOption],
                                          request: RoutePlanRequest,
                                          segment_features: List[List[SegmentFeature]],
                                          config: Phase2Configuration) -> List[RouteOption]:
        """Apply detour optimization to route options"""
        
        optimized_routes = []
        route_weights = self._convert_request_to_weights(request)
        
        # Create detour constraints from config and request
        detour_constraints = DetourConstraints(
            max_count=getattr(request, 'max_detours', config.max_detours),
            radius_km=getattr(request, 'detour_radius_km', config.detour_radius_km),
            min_gain=config.min_detour_gain
        )
        
        per_route_budget = config.detour_optimization_budget / len(route_options) if route_options else 0
        
        for i, route_option in enumerate(route_options):
            try:
                # Convert RouteOption to dict for detour optimizer
                baseline_route = self._route_option_to_dict(route_option)
                
                # Optimize with detours
                optimization_result = await self.detour_optimizer.optimize_route_with_detours(
                    baseline_route,
                    route_weights,
                    detour_constraints,
                    per_route_budget
                )
                
                # Convert back to RouteOption with detour enhancements
                enhanced_route = self._dict_to_enhanced_route_option(
                    route_option, optimization_result
                )
                
                optimized_routes.append(enhanced_route)
                self.integration_stats["detours_optimized"] += len(optimization_result.accepted_detours)
                
            except Exception as e:
                logger.error(f"Detour optimization failed for route {i}: {e}")
                # Use original route as fallback
                optimized_routes.append(route_option)
        
        return optimized_routes

    def _route_option_to_dict(self, route_option: RouteOption) -> Dict[str, Any]:
        """Convert RouteOption to dict format for detour optimizer"""
        
        return {
            'route_id': route_option.route_id,
            'geometry': route_option.route_data.get('geometry', {}) if route_option.route_data else {},
            'distance_m': route_option.distance_m,
            'duration_s': route_option.duration_s,
            'coordinates': self._extract_coordinates_from_route_data(route_option.route_data)
        }

    def _extract_coordinates_from_route_data(self, route_data: Dict[str, Any]) -> List[Dict[str, float]]:
        """Extract coordinates from route data"""
        
        coordinates = []
        
        if route_data and 'geometry' in route_data:
            geometry = route_data['geometry']
            
            if 'coordinates' in geometry:
                coords = geometry['coordinates']
                coordinates = [
                    {'longitude': c[0], 'latitude': c[1]}
                    for c in coords[:100]  # Limit for performance
                ]
        
        return coordinates

    def _dict_to_enhanced_route_option(self,
                                     original: RouteOption,
                                     optimization_result: DetourOptimizationResult) -> RouteOption:
        """Convert optimization result back to enhanced RouteOption"""
        
        # Create enhanced route option with detour data
        enhanced = RouteOption(
            route_id=original.route_id,
            name=f"{original.name} + {len(optimization_result.accepted_detours)} detours",
            route_data=optimization_result.enhanced_route,
            distance_m=original.distance_m + (optimization_result.total_distance_added_km * 1000),
            duration_s=original.duration_s + (optimization_result.total_time_added_min * 60),
            ascent_m=original.ascent_m,
            descent_m=original.descent_m,
            off_pavement_pct=original.off_pavement_pct,  # Would recalculate with detours
            surface_mix=original.surface_mix,
            road_class_mix=original.road_class_mix,
            confidence=original.confidence,
            flags=original.flags,
            detours=original.detours + [
                {
                    'detour_id': d.detour_id,
                    'type': d.detour_type.value,
                    'dirt_gain': d.dirt_gain,
                    'scenic_gain': d.scenic_gain,
                    'distance_km': d.detour_distance_km
                }
                for d in optimization_result.accepted_detours
            ],
            diagnostics=original.diagnostics
        )
        
        return enhanced

    async def _enhance_route_options(self,
                                   route_options: List[RouteOption],
                                   segment_features: List[List[SegmentFeature]],
                                   custom_models: Dict[AdvVariant, ModelConfiguration],
                                   config: Phase2Configuration) -> List[RouteOption]:
        """Enhance route options with Phase 2 analytics"""
        
        enhanced_options = []
        
        for i, route_option in enumerate(route_options):
            try:
                # Get segment features for this route
                route_features = segment_features[i] if i < len(segment_features) else []
                
                # Calculate enhanced metrics from segment features
                enhanced_metrics = self._calculate_enhanced_metrics(route_features)
                
                # Add model confidence scores
                model_scores = self._calculate_model_scores(route_features, custom_models)
                
                # Update route option with enhanced data
                enhanced_option = self._add_phase2_enhancements(
                    route_option, enhanced_metrics, model_scores, route_features
                )
                
                enhanced_options.append(enhanced_option)
                
            except Exception as e:
                logger.error(f"Route enhancement failed for route {i}: {e}")
                enhanced_options.append(route_option)
        
        return enhanced_options

    def _calculate_enhanced_metrics(self, features: List[SegmentFeature]) -> Dict[str, float]:
        """Calculate enhanced metrics from segment features"""
        
        if not features:
            return {}
        
        # Aggregate feature scores
        avg_dirt_score = sum(f.dirt_score for f in features) / len(features)
        avg_scenic_score = sum(f.scenic_score for f in features) / len(features)
        avg_risk_score = sum(f.risk_score for f in features) / len(features)
        avg_popularity = sum(f.popularity_score for f in features) / len(features)
        
        # Calculate curvature metrics
        avg_curvature = sum(f.curvature_mean for f in features) / len(features)
        max_curvature = max(f.curvature_p95 for f in features)
        
        # Calculate grade metrics
        avg_grade = sum(f.grade_mean_pct for f in features) / len(features)
        steep_segments_pct = sum(1 for f in features if f.pct_over_12_pct > 20) / len(features) * 100
        
        return {
            'dirt_score': avg_dirt_score,
            'scenic_score': avg_scenic_score,
            'risk_score': avg_risk_score,
            'popularity_score': avg_popularity,
            'curvature_mean': avg_curvature,
            'curvature_max': max_curvature,
            'grade_mean_pct': avg_grade,
            'steep_segments_pct': steep_segments_pct
        }

    def _calculate_model_scores(self,
                              features: List[SegmentFeature],
                              models: Dict[AdvVariant, ModelConfiguration]) -> Dict[str, float]:
        """Calculate routing model confidence scores"""
        
        scores = {}
        
        for variant, model in models.items():
            # Use model confidence as base score
            score = model.confidence
            
            # Adjust based on feature alignment with model variant
            if features:
                avg_dirt = sum(f.dirt_score for f in features) / len(features)
                avg_risk = sum(f.risk_score for f in features) / len(features)
                
                # Variant-specific adjustments
                if variant == AdvVariant.ADV_EASY:
                    # Easy routes should have lower risk
                    if avg_risk < 0.3:
                        score += 0.1
                    elif avg_risk > 0.6:
                        score -= 0.2
                        
                elif variant == AdvVariant.ADV_TECH:
                    # Technical routes should have higher dirt scores
                    if avg_dirt > 0.7:
                        score += 0.1
                    elif avg_dirt < 0.4:
                        score -= 0.1
            
            scores[f"{variant.value}_confidence"] = max(0.0, min(1.0, score))
        
        return scores

    def _add_phase2_enhancements(self,
                               route_option: RouteOption,
                               enhanced_metrics: Dict[str, float],
                               model_scores: Dict[str, float],
                               segment_features: List[SegmentFeature]) -> RouteOption:
        """Add Phase 2 enhancements to route option"""
        
        # Update diagnostics with Phase 2 data
        enhanced_diagnostics = route_option.diagnostics.copy()
        enhanced_diagnostics.update({
            'phase2_enabled': True,
            'segment_features_count': len(segment_features),
            'enhanced_metrics': enhanced_metrics,
            'model_scores': model_scores,
            'feature_extraction_success': len(segment_features) > 0
        })
        
        # Create enhanced route option
        enhanced_option = RouteOption(
            route_id=route_option.route_id,
            name=route_option.name,
            route_data=route_option.route_data,
            distance_m=route_option.distance_m,
            duration_s=route_option.duration_s,
            ascent_m=route_option.ascent_m,
            descent_m=route_option.descent_m,
            off_pavement_pct=route_option.off_pavement_pct,
            surface_mix=route_option.surface_mix,
            road_class_mix=route_option.road_class_mix,
            confidence=route_option.confidence,
            flags=route_option.flags,
            detours=route_option.detours,
            diagnostics=enhanced_diagnostics
        )
        
        return enhanced_option

    async def _build_phase2_result(self,
                                 baseline_result: Dict[str, Any],
                                 enhanced_options: List[RouteOption],
                                 segment_features: List[List[SegmentFeature]],
                                 custom_models: Dict[AdvVariant, ModelConfiguration],
                                 start_time: float,
                                 config: Phase2Configuration) -> Dict[str, Any]:
        """Build comprehensive Phase 2 result"""
        
        # Build enhanced result based on baseline
        phase2_result = baseline_result.copy()
        phase2_result['route_options'] = enhanced_options
        
        # Add Phase 2 specific diagnostics
        phase2_diagnostics = {
            'phase2_enabled': True,
            'processing_time_s': time.time() - start_time,
            'segment_features_extracted': sum(len(features) for features in segment_features),
            'custom_models_built': len(custom_models),
            'configuration': {
                'segment_features': config.enable_segment_features,
                'custom_models': config.enable_custom_models,
                'detour_optimization': config.enable_detour_optimization
            },
            'model_explanations': {
                variant.value: self.model_builder.get_model_explanation(model)
                for variant, model in custom_models.items()
            }
        }
        
        # Merge with existing diagnostics
        if 'diagnostics' in phase2_result:
            phase2_result['diagnostics'].update(phase2_diagnostics)
        else:
            phase2_result['diagnostics'] = phase2_diagnostics
        
        # Update stats
        phase2_stats = phase2_result.get('stats', {})
        phase2_stats.update({
            'phase2_enabled': True,
            'enhanced_features': config.enable_segment_features,
            'custom_routing': config.enable_custom_models,
            'detour_optimization': config.enable_detour_optimization
        })
        phase2_result['stats'] = phase2_stats
        
        return phase2_result

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in kilometers"""
        import math
        
        R = 6371.0  # Earth radius in km
        
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