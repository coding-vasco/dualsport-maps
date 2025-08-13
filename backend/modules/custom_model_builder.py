"""
Custom Model Builder Module - Phase 2
Builds OpenRouteService routing profiles from user preferences and segment features.

Adapts the GraphHopper Custom Model concept to work with OpenRouteService by:
- Converting user weights to ORS avoid_features and preferences
- Creating variant profiles (ADV_EASY, ADV_MIXED, ADV_TECH)
- Applying per-edge penalties based on segment features
"""

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .segment_features import SegmentFeature

logger = logging.getLogger(__name__)

class AdvVariant(Enum):
    """ADV route variants with different risk/difficulty profiles"""
    ADV_EASY = "ADV_EASY"
    ADV_MIXED = "ADV_MIXED" 
    ADV_TECH = "ADV_TECH"

@dataclass
class RouteWeights:
    """User-specified routing weights and preferences"""
    dirt: float = 0.6          # Preference for dirt/gravel surfaces
    scenic: float = 0.4        # Preference for scenic routes
    risk: float = -0.2         # Risk tolerance (negative = avoid risk)
    popularity: float = 0.2    # Weight for popular routes
    
    # Surface preferences
    prefer_surfaces: List[str] = None
    avoid_surfaces: List[str] = None
    
    # Road class preferences  
    minimize_classes: List[str] = None
    
    # Thresholds
    avoid_steep_over_pct: float = 14.0
    off_pavement_target_pct: float = 60.0

@dataclass
class ModelConfiguration:
    """Complete routing model configuration for ORS"""
    base_profile: str           # 'cycling-regular', 'driving-car', etc.
    avoid_features: List[str]   # ORS avoid_features
    options: Dict[str, Any]     # ORS routing options
    variant: AdvVariant         # ADV variant being used
    weights: RouteWeights       # Original user weights
    confidence: float           # Model confidence (0-1)
    
class CustomModelBuilder:
    """Build OpenRouteService routing models from user preferences"""
    
    def __init__(self):
        # ORS profile mappings
        self.base_profiles = {
            AdvVariant.ADV_EASY: "cycling-regular",    # More conservative
            AdvVariant.ADV_MIXED: "cycling-regular",   # Balanced  
            AdvVariant.ADV_TECH: "cycling-regular"     # More aggressive
        }
        
        # Available ORS avoid features (limited compared to GraphHopper)
        self.ors_avoid_features = {
            'highways', 'tollways', 'ferries', 'fords', 'steps'
        }
        
        # Surface preference mappings for ORS
        self.surface_avoid_mapping = {
            'sand': 'unpaved',      # ORS doesn't have granular surface control
            'mud': 'unpaved',
            'grass': 'unpaved'
        }
        
        # Road class avoid mappings
        self.road_class_avoid_mapping = {
            'motorway': 'highways',
            'trunk': 'highways', 
            'primary': None,        # ORS can't avoid primary specifically
            'secondary': None,
            'tertiary': None
        }
        
        self.model_stats = {
            "models_built": 0,
            "variants_generated": 0,
            "feature_penalties_applied": 0,
            "errors": 0
        }

    def build_routing_model(self,
                          weights: RouteWeights,
                          variant: AdvVariant,
                          segment_features: List[SegmentFeature] = None) -> ModelConfiguration:
        """
        Build complete routing model configuration for ORS
        
        Args:
            weights: User routing preferences and weights
            variant: ADV variant (EASY/MIXED/TECH)
            segment_features: Optional segment features for fine-tuning
            
        Returns:
            ModelConfiguration with ORS-compatible settings
        """
        
        try:
            logger.info(f"Building {variant.value} routing model")
            
            # Get base profile for variant
            base_profile = self.base_profiles[variant]
            
            # Build avoid features list
            avoid_features = self._build_avoid_features(weights, variant)
            
            # Build routing options
            options = self._build_routing_options(weights, variant, segment_features)
            
            # Calculate model confidence
            confidence = self._calculate_model_confidence(weights, variant, segment_features)
            
            model_config = ModelConfiguration(
                base_profile=base_profile,
                avoid_features=avoid_features,
                options=options,
                variant=variant,
                weights=weights,
                confidence=confidence
            )
            
            self.model_stats["models_built"] += 1
            self.model_stats["variants_generated"] += 1
            
            logger.info(f"Built {variant.value} model with confidence {confidence:.2f}")
            return model_config
            
        except Exception as e:
            logger.error(f"Model building failed for {variant.value}: {e}")
            self.model_stats["errors"] += 1
            return self._build_fallback_model(weights, variant)

    def _build_avoid_features(self,
                            weights: RouteWeights, 
                            variant: AdvVariant) -> List[str]:
        """Build ORS avoid_features list based on weights and variant"""
        
        avoid_features = []
        
        # Always avoid ferries for ADV routes
        avoid_features.append('ferries')
        
        # Variant-specific avoidances
        if variant == AdvVariant.ADV_EASY:
            avoid_features.extend(['highways', 'tollways'])
            # More conservative - avoid fords for easy routes
            avoid_features.append('fords')
            
        elif variant == AdvVariant.ADV_MIXED:
            avoid_features.append('highways')
            # Mixed - allow tollways and fords
            
        elif variant == AdvVariant.ADV_TECH:
            # Technical routes - only avoid highways if explicitly requested
            if weights.minimize_classes and 'motorway' in weights.minimize_classes:
                avoid_features.append('highways')
        
        # Apply user road class preferences
        if weights.minimize_classes:
            for road_class in weights.minimize_classes:
                ors_avoid = self.road_class_avoid_mapping.get(road_class)
                if ors_avoid and ors_avoid not in avoid_features:
                    avoid_features.append(ors_avoid)
        
        # Apply surface avoidances (limited in ORS)
        if weights.avoid_surfaces:
            for surface in weights.avoid_surfaces:
                ors_avoid = self.surface_avoid_mapping.get(surface)
                if ors_avoid and ors_avoid not in avoid_features:
                    avoid_features.append(ors_avoid)
        
        # Remove duplicates and invalid features
        valid_features = [f for f in set(avoid_features) if f in self.ors_avoid_features]
        
        return valid_features

    def _build_routing_options(self,
                             weights: RouteWeights,
                             variant: AdvVariant,
                             segment_features: List[SegmentFeature]) -> Dict[str, Any]:
        """Build ORS routing options based on preferences"""
        
        options = {}
        
        # Variant-specific option tuning
        if variant == AdvVariant.ADV_EASY:
            # Easy routes - prefer smoother surfaces, avoid technical terrain
            options.update({
                "avoid_borders": False,
                "avoid_countries": [],
                "vehicle_type": "cycling"  # More conservative routing
            })
            
        elif variant == AdvVariant.ADV_MIXED:
            # Mixed routes - balanced approach
            options.update({
                "avoid_borders": False,
                "vehicle_type": "cycling"
            })
            
        elif variant == AdvVariant.ADV_TECH:
            # Technical routes - allow more adventurous routing
            options.update({
                "avoid_borders": False,
                "vehicle_type": "cycling"
            })
        
        # Apply segment feature penalties if available
        if segment_features:
            feature_options = self._apply_segment_feature_penalties(
                segment_features, weights, variant
            )
            options.update(feature_options)
        
        return options

    def _apply_segment_feature_penalties(self,
                                       segment_features: List[SegmentFeature],
                                       weights: RouteWeights,
                                       variant: AdvVariant) -> Dict[str, Any]:
        """Apply penalties based on analyzed segment features"""
        
        # Note: ORS has limited custom penalty support compared to GraphHopper
        # This function prepares data that could be used for post-processing
        
        options = {}
        
        # Analyze segment features to derive routing hints
        if segment_features:
            # Calculate average feature scores
            avg_dirt_score = sum(sf.dirt_score for sf in segment_features) / len(segment_features)
            avg_scenic_score = sum(sf.scenic_score for sf in segment_features) / len(segment_features)
            avg_risk_score = sum(sf.risk_score for sf in segment_features) / len(segment_features)
            
            # Store feature analysis for post-route processing
            options["feature_analysis"] = {
                "avg_dirt_score": avg_dirt_score,
                "avg_scenic_score": avg_scenic_score,
                "avg_risk_score": avg_risk_score,
                "segment_count": len(segment_features),
                "high_risk_segments": sum(1 for sf in segment_features if sf.risk_score > 0.7),
                "high_dirt_segments": sum(1 for sf in segment_features if sf.dirt_score > 0.8),
                "steep_segments": sum(1 for sf in segment_features if sf.pct_over_12_pct > 20)
            }
            
            # Apply variant-specific adjustments based on features
            if variant == AdvVariant.ADV_EASY and avg_risk_score > 0.6:
                # High risk detected - add more conservative options
                options["prefer_green"] = True  # Prefer quieter routes
                
            elif variant == AdvVariant.ADV_TECH and avg_dirt_score > 0.8:
                # High dirt potential - allow more adventurous routing
                options["allow_unsuitable"] = True
            
            self.model_stats["feature_penalties_applied"] += len(segment_features)
        
        return options

    def _calculate_model_confidence(self,
                                  weights: RouteWeights,
                                  variant: AdvVariant,
                                  segment_features: List[SegmentFeature]) -> float:
        """Calculate confidence in the routing model (0-1)"""
        
        confidence = 0.7  # Base confidence for ORS
        
        # Boost confidence if we have segment features
        if segment_features:
            confidence += 0.1
            
            # Additional boost for good feature coverage
            if len(segment_features) > 10:
                confidence += 0.1
        
        # Variant-specific confidence adjustments
        if variant == AdvVariant.ADV_EASY:
            confidence += 0.1  # Easy routes are more predictable
        elif variant == AdvVariant.ADV_TECH:
            confidence -= 0.1  # Technical routes are less predictable
        
        # Penalize extreme weight combinations
        total_weight = abs(weights.dirt) + abs(weights.scenic) + abs(weights.risk)
        if total_weight > 2.0:  # Very extreme preferences
            confidence -= 0.2
        
        # Penalize conflicting preferences
        if weights.dirt > 0.8 and weights.risk < -0.5:
            confidence -= 0.1  # Want dirt but avoid all risk
        
        return max(0.1, min(1.0, confidence))

    def build_variant_models(self,
                           weights: RouteWeights,
                           variants: List[AdvVariant] = None,
                           segment_features: List[SegmentFeature] = None) -> Dict[AdvVariant, ModelConfiguration]:
        """Build multiple variant models for route comparison"""
        
        if variants is None:
            variants = [AdvVariant.ADV_EASY, AdvVariant.ADV_MIXED, AdvVariant.ADV_TECH]
        
        models = {}
        
        for variant in variants:
            try:
                model = self.build_routing_model(weights, variant, segment_features)
                models[variant] = model
                
            except Exception as e:
                logger.error(f"Failed to build {variant.value} model: {e}")
                models[variant] = self._build_fallback_model(weights, variant)
        
        logger.info(f"Built {len(models)} variant models")
        return models

    def adapt_model_for_detours(self,
                              base_model: ModelConfiguration,
                              detour_segments: List[SegmentFeature]) -> ModelConfiguration:
        """Adapt model for specific detour segments"""
        
        # Create modified model for detour evaluation
        adapted_options = base_model.options.copy()
        
        if detour_segments:
            # Analyze detour segments
            avg_dirt_score = sum(sf.dirt_score for sf in detour_segments) / len(detour_segments)
            avg_risk_score = sum(sf.risk_score for sf in detour_segments) / len(detour_segments)
            
            # Adjust options for detour characteristics
            if avg_dirt_score > 0.8:
                # High dirt detour - allow more adventurous routing
                adapted_options["detour_dirt_bonus"] = avg_dirt_score
                
            if avg_risk_score > 0.7:
                # High risk detour - add caution flags
                adapted_options["detour_risk_warning"] = avg_risk_score
        
        # Create adapted model
        adapted_model = ModelConfiguration(
            base_profile=base_model.base_profile,
            avoid_features=base_model.avoid_features,
            options=adapted_options,
            variant=base_model.variant,
            weights=base_model.weights,
            confidence=base_model.confidence * 0.9  # Slightly lower confidence for adapted model
        )
        
        return adapted_model

    def get_model_explanation(self, model: ModelConfiguration) -> Dict[str, Any]:
        """Generate human-readable explanation of routing model"""
        
        explanation = {
            "variant": model.variant.value,
            "base_profile": model.base_profile,
            "confidence": model.confidence,
            "key_settings": [],
            "avoid_list": model.avoid_features,
            "preferences": []
        }
        
        # Explain variant characteristics
        variant_explanations = {
            AdvVariant.ADV_EASY: "Conservative ADV routing with smoother surfaces and lower risk",
            AdvVariant.ADV_MIXED: "Balanced ADV routing mixing pavement and dirt with moderate challenge", 
            AdvVariant.ADV_TECH: "Aggressive ADV routing favoring technical terrain and off-pavement"
        }
        
        explanation["description"] = variant_explanations[model.variant]
        
        # Explain weight preferences
        weights = model.weights
        if weights.dirt > 0.6:
            explanation["preferences"].append(f"Strong dirt preference ({weights.dirt:.1f})")
        if weights.scenic > 0.5:
            explanation["preferences"].append(f"Scenic routing emphasis ({weights.scenic:.1f})")
        if weights.risk < -0.3:
            explanation["preferences"].append(f"Risk avoidance ({weights.risk:.1f})")
        
        # Explain avoid features
        avoid_explanations = {
            'highways': "Avoiding highways/motorways",
            'tollways': "Avoiding toll roads", 
            'ferries': "Avoiding ferries",
            'fords': "Avoiding water crossings",
            'unpaved': "Avoiding unpaved surfaces"
        }
        
        explanation["key_settings"] = [
            avoid_explanations.get(feature, f"Avoiding {feature}")
            for feature in model.avoid_features
        ]
        
        return explanation

    def _build_fallback_model(self,
                            weights: RouteWeights,
                            variant: AdvVariant) -> ModelConfiguration:
        """Build minimal fallback model when main building fails"""
        
        return ModelConfiguration(
            base_profile="cycling-regular",
            avoid_features=["ferries"],  # Minimal safe defaults
            options={},
            variant=variant,
            weights=weights,
            confidence=0.3  # Low confidence for fallback
        )

    def export_model_for_ors(self, model: ModelConfiguration) -> Dict[str, Any]:
        """Export model in format suitable for ORS API calls"""
        
        ors_payload = {
            "profile": model.base_profile,
            "format": "geojson",
            "instructions": True,
            "elevation": True,
            "extra_info": ["surface", "waytype", "steepness"],
            "options": {
                "avoid_features": model.avoid_features,
                **model.options
            }
        }
        
        # Add model metadata for diagnostics
        ors_payload["model_metadata"] = {
            "variant": model.variant.value,
            "confidence": model.confidence,
            "weights": {
                "dirt": model.weights.dirt,
                "scenic": model.weights.scenic,
                "risk": model.weights.risk,
                "popularity": model.weights.popularity
            }
        }
        
        return ors_payload

# Factory functions for common model configurations

def create_preset_weights(preset: str) -> RouteWeights:
    """Create preset weight configurations"""
    
    presets = {
        "beginner": RouteWeights(
            dirt=0.3, scenic=0.4, risk=-0.5, popularity=0.3,
            avoid_steep_over_pct=10.0,
            off_pavement_target_pct=30.0
        ),
        "intermediate": RouteWeights(
            dirt=0.6, scenic=0.4, risk=-0.2, popularity=0.2,
            avoid_steep_over_pct=14.0,
            off_pavement_target_pct=60.0
        ),
        "advanced": RouteWeights(
            dirt=0.8, scenic=0.3, risk=0.1, popularity=0.1,
            avoid_steep_over_pct=18.0,
            off_pavement_target_pct=80.0
        ),
        "scenic": RouteWeights(
            dirt=0.4, scenic=0.8, risk=-0.3, popularity=0.3,
            avoid_steep_over_pct=12.0,
            off_pavement_target_pct=40.0
        )
    }
    
    return presets.get(preset, presets["intermediate"])

def build_quick_model(preset: str, variant: AdvVariant = AdvVariant.ADV_MIXED) -> ModelConfiguration:
    """Quick model builder with presets"""
    
    builder = CustomModelBuilder()
    weights = create_preset_weights(preset)
    
    return builder.build_routing_model(weights, variant)