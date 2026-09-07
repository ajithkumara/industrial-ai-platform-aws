"""
NATS Bearing Bridge Entry Point
python -m edge.run_nats_bridge

Bridges adaptive-edge-orchestrator's NATS-published bearing sensor,
inference, mode-transition, and context-snapshot events onto Event Hub,
in the generic TelemetryEvent envelope, as the bearing_sensor /
bearing_inference / orchestrator_mode / context_snapshot asset types.
(cloud_validation is NOT bridged here -- it's produced cloud-side by the
CloudForest scoring job. See config/asset_types/cloud_validation.yml.)

Requires `nats-py` (see requirements.txt) and NATS_URL /
NATS_BEARING_SENSOR_SUBJECT / NATS_BEARING_INFERENCE_SUBJECT /
NATS_ORCHESTRATOR_MODE_SUBJECT / NATS_CONTEXT_SNAPSHOT_SUBJECT in .env
if your NATS setup differs from the defaults (config/settings.py).
"""

from __future__ import annotations

import asyncio
import logging

from config.settings import settings
from .nats_bearing_bridge import NatsBearingBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Starting NATS bearing bridge...")

    bridge = NatsBearingBridge(
        nats_url=settings.nats.url,
        sensor_subject=settings.nats.bearing_sensor_subject,
        inference_subject=settings.nats.bearing_inference_subject,
        mode_subject=settings.nats.orchestrator_mode_subject,
        context_subject=settings.nats.context_snapshot_subject,
    )

    try:
        await bridge.run()
    except KeyboardInterrupt:
        logger.info("Stopping NATS bearing bridge...")
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
