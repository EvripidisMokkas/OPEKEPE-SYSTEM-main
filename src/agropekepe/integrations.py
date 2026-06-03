"""Integration adapters for map, satellite, weather, tax, and payment systems.

The MVP keeps these adapters deterministic and dependency-free. Production
implementations can replace them with authenticated clients for Google Earth
Engine, Google Maps Platform, AADE myDATA, weather feeds, cadastral systems, and
bank/payment rails without changing the service-layer contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from agropekepe.models import Parcel, RemoteSensingObservation, new_id


@dataclass(frozen=True)
class GoogleMapsParcelView:
    """Map display metadata for parcel review and editing."""

    parcel_id: str
    center_lat: Decimal
    center_lon: Decimal
    zoom: int
    maps_url: str


@dataclass(frozen=True)
class EarthEngineCropSignal:
    """Remote-sensing result normalized from an Earth Engine processing job."""

    parcel_id: str
    claim_year: int
    predicted_label: str
    confidence: Decimal
    ndvi_trend: str
    evidence_uri: str


@dataclass(frozen=True)
class WeatherAlert:
    """Weather or disaster alert normalized for crisis workflows."""

    event_type: str
    claim_year: int
    confidence: Decimal
    severity: str
    evidence_uri: str


class GoogleMapsAdapter:
    """Build Google Maps display links for parcel workflows."""

    def parcel_view(self, parcel: Parcel, zoom: int = 17) -> GoogleMapsParcelView:
        """Return deterministic map metadata for a parcel centroid."""

        return GoogleMapsParcelView(
            parcel_id=parcel.parcel_id,
            center_lat=parcel.centroid_lat,
            center_lon=parcel.centroid_lon,
            zoom=zoom,
            maps_url=f"https://www.google.com/maps/@{parcel.centroid_lat},{parcel.centroid_lon},{zoom}z",
        )


class EarthEngineAdapter:
    """Normalize Google Earth Engine crop/damage outputs into ledger evidence."""

    def crop_signal_to_observation(self, signal: EarthEngineCropSignal) -> RemoteSensingObservation:
        """Convert a crop classification signal to a ledger observation."""

        return RemoteSensingObservation(
            observation_id=new_id(),
            parcel_id=signal.parcel_id,
            claim_year=signal.claim_year,
            provider="google-earth-engine",
            observation_type="crop_classification",
            confidence=signal.confidence,
            result={"predicted_label": signal.predicted_label, "ndvi_trend": signal.ndvi_trend},
            evidence_uri=signal.evidence_uri,
        )

    def weather_alert_to_observation(self, parcel_id: str, alert: WeatherAlert) -> RemoteSensingObservation:
        """Convert a weather/disaster alert into parcel-level crisis evidence."""

        return RemoteSensingObservation(
            observation_id=new_id(),
            parcel_id=parcel_id,
            claim_year=alert.claim_year,
            provider="weather-or-earth-engine-alert",
            observation_type=alert.event_type,
            confidence=alert.confidence,
            result={"severity": alert.severity},
            evidence_uri=alert.evidence_uri,
        )
