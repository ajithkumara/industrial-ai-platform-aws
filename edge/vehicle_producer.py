"""
Telemetry Simulator

Generates realistic vehicle telemetry for Azure Event Hub,
wrapped in the generic TelemetryEvent envelope consumed by the pipeline.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, UTC


class VehicleTelemetryGenerator:
    """
    Generates mock vehicle telemetry wrapped in the generic envelope.
    """

    VEHICLES = [
        "CAR-001",
        "CAR-002",
        "CAR-003",
        "CAR-004",
        "CAR-005",
    ]

    DRIVERS = [
        "DRV-101",
        "DRV-102",
        "DRV-103",
        "DRV-104",
        "DRV-105",
    ]

    def generate(self) -> dict:
        """
        Returns a dict that matches the TelemetryEvent generic envelope.
        Vehicle-specific data is nested inside `payload`.
        """

        vehicle_id = random.choice(self.VEHICLES)

        return {
            "event_id": str(uuid.uuid4()),
            "device_id": vehicle_id,
            "asset_type": "vehicle",
            "timestamp": datetime.now(UTC).isoformat(),
            "priority": "normal",
            "schema_version": "1.0.0",
            "payload": {
                "vehicle_id": vehicle_id,
                "driver_id": random.choice(self.DRIVERS),
                "location": {
                    "latitude": round(random.uniform(43.42, 43.55), 6),
                    "longitude": round(random.uniform(-79.79, -79.62), 6),
                },
                "speed_kmh": random.randint(0, 120),
                "heading": random.randint(0, 359),
                "fuel_level_percent": random.randint(15, 100),
                "engine_temperature_c": round(random.uniform(78.0, 104.0), 1),
                "battery_voltage": round(random.uniform(12.2, 14.4), 2),
                "odometer_km": round(random.uniform(1000, 90000), 1),
                "ignition": random.choice([True, True, True, False]),
            },
        }