"""
Mictrack MP91 TCP Listener
==========================
Receives ASCII telemetry packets from the Mictrack MP91 4G OBD tracker
over a persistent TCP connection and feeds parsed events into the
Kinesis pipeline via KinesisProducer.

Device setup (send SMS to device SIM):
    SERVER,1,<THIS_SERVER_IP>,5013,0#
    TIMER,30#
    RESTART#

Run (from repo root):
    set KINESIS_STREAM_NAME=iap-dev-telemetryhub
    set AWS_DEFAULT_REGION=ca-central-1
    set AWS_PROFILE=iap-dev
    python -m edge.tcp_listener

Or directly:
    python edge/tcp_listener.py

Environment variables:
    TCP_HOST            Bind address (default: 0.0.0.0)
    TCP_PORT            Listen port  (default: 5013)
    KINESIS_STREAM_NAME Kinesis stream (default: iap-dev-telemetryhub)
    AWS_DEFAULT_REGION  AWS region   (default: ca-central-1)
    DEVICE_ID_PREFIX    Prefix for auto-assigned device IDs (default: mp91)
    LOG_LEVEL           DEBUG / INFO / WARNING (default: INFO)

Protocol notes (Mictrack MP91 open ASCII):
    The device sends lines terminated by \\r\\n over TCP.
    A typical position packet looks like:
        $$<len>,<imei>,AAA,<date>,<time>,<lat>,<ns>,<lon>,<ew>,<speed>,<course>,<valid>,...<checksum>\\r\\n
    We parse what we can and put the rest in raw_payload so nothing is lost.
    If the format changes, update _parse_packet() — the pipeline contract
    (device_id, latitude, longitude, speed_kmh, timestamp, asset_type) stays fixed.

Author: Ajith Kumara
Project: Industrial AI Platform (AWS) — Edge
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

UTC = timezone.utc

# ── logging ───────────────────────────────────────────────────────────────────

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s | %(levelname)s | [%(threadName)s] %(message)s",
)
log = logging.getLogger("mp91_listener")


# ── config ────────────────────────────────────────────────────────────────────

HOST: str = os.environ.get("TCP_HOST", "0.0.0.0")
PORT: int = int(os.environ.get("TCP_PORT", "5013"))
DEVICE_ID_PREFIX: str = os.environ.get("DEVICE_ID_PREFIX", "mp91")

# Lazy-import KinesisProducer so the listener can be tested without AWS creds
# (just set KINESIS_DRY_RUN=1 to print events instead of sending them).
DRY_RUN: bool = os.environ.get("KINESIS_DRY_RUN", "0") == "1"


# ── packet parser ─────────────────────────────────────────────────────────────

# Mictrack open ASCII packet pattern (simplified — covers common MP91 output).
# Full spec available from Mictrack on request; this covers position packets.
#
# Example:
#   $$76,865280051234567,AAA,250909,141523,43.6532,N,79.3832,W,55.3,270.1,1,12,1.2,0,0,0000,2*AB
#   $$<len>,<imei>,<cmd>,<date:YYMMDD>,<time:HHMMSS>,<lat>,<N/S>,<lon>,<E/W>,
#      <speed_knots>,<course>,<valid:1=fix>,<sats>,<hdop>,<altitude>,<mileage>,
#      <io_status>,<voltage>*<checksum>

_POSITION_RE = re.compile(
    r"\$\$\d+,"               # $$ + length
    r"(?P<imei>\d{14,15}),"   # IMEI
    r"[A-Z]{3},"              # command code (AAA=position, etc.)
    r"(?P<date>\d{6}),"       # YYMMDD
    r"(?P<time>\d{6}),"       # HHMMSS
    r"(?P<lat>[\d.]+),"       # latitude
    r"(?P<ns>[NS]),"          # N or S
    r"(?P<lon>[\d.]+),"       # longitude
    r"(?P<ew>[EW]),"          # E or W
    r"(?P<speed>[\d.]+),"     # speed in knots
    r"(?P<course>[\d.]+),"    # course (degrees)
    r"(?P<valid>[01])"        # GPS fix valid
)

# Heartbeat / login packets — acknowledge but don't forward to Kinesis
_HEARTBEAT_RE = re.compile(r"^\$\$\d+,[^,]+,HBT", re.IGNORECASE)
_LOGIN_RE = re.compile(r"^\$\$\d+,[^,]+,LOG", re.IGNORECASE)


def _parse_packet(raw: str) -> Optional[dict]:
    """
    Parse a raw ASCII line from the MP91 into a platform event envelope.
    Returns None for heartbeat/login packets that should not be forwarded.
    Returns a dict with the platform event schema on success.
    Returns a partial dict with raw_payload on parse failure (for DLQ).
    """
    raw = raw.strip()
    if not raw:
        return None

    # Heartbeat / login — no position data
    if _HEARTBEAT_RE.match(raw) or _LOGIN_RE.match(raw):
        log.debug("Heartbeat/login packet — acknowledged, not forwarded: %r", raw[:60])
        return None

    m = _POSITION_RE.match(raw)
    if not m:
        log.warning("Unrecognised packet format — forwarding as raw: %r", raw[:80])
        return {
            "event_id": str(uuid.uuid4()),
            "device_id": f"{DEVICE_ID_PREFIX}-unknown",
            "asset_type": "vehicle",
            "timestamp": datetime.now(UTC).isoformat(),
            "schema_version": "1.0",
            "source": "mp91_tcp",
            "raw_payload": raw,
            "_parse_error": "unrecognised_format",
        }

    imei = m.group("imei")
    device_id = f"{DEVICE_ID_PREFIX}-{imei}"

    # Build UTC timestamp from device date/time (device sends local or UTC — assume UTC)
    try:
        date_str = m.group("date")   # YYMMDD
        time_str = m.group("time")   # HHMMSS
        ts = datetime.strptime(f"20{date_str}{time_str}", "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        timestamp = ts.isoformat()
    except ValueError:
        timestamp = datetime.now(UTC).isoformat()

    # Latitude / longitude
    lat = float(m.group("lat"))
    if m.group("ns") == "S":
        lat = -lat
    lon = float(m.group("lon"))
    if m.group("ew") == "W":
        lon = -lon

    # Speed: knots → km/h
    speed_knots = float(m.group("speed"))
    speed_kmh = round(speed_knots * 1.852, 1)

    gps_valid = m.group("valid") == "1"

    return {
        "event_id": str(uuid.uuid4()),
        "device_id": device_id,
        "asset_type": "vehicle",
        "timestamp": timestamp,
        "schema_version": "1.0",
        "source": "mp91_tcp",
        "payload": {
            "imei": imei,
            "latitude": lat,
            "longitude": lon,
            "speed_kmh": speed_kmh,
            "course_deg": float(m.group("course")),
            "gps_valid": gps_valid,
        },
        "raw_payload": raw,
    }


# ── Kinesis sender ────────────────────────────────────────────────────────────

class _ProducerWrapper:
    """Thin wrapper so dry-run mode works without boto3 / Kinesis available."""

    def __init__(self) -> None:
        if DRY_RUN:
            log.info("DRY RUN mode — events will be printed, not sent to Kinesis.")
            self._producer = None
        else:
            from edge.base_producer import KinesisProducer  # type: ignore
            self._producer = KinesisProducer()

    def send(self, event: dict) -> None:
        if DRY_RUN or self._producer is None:
            log.info("DRY RUN event: %s", json.dumps(event, indent=2))
            return
        try:
            self._producer.send_events([event])
        except Exception as exc:
            log.error("Failed to send event to Kinesis: %s", exc)
            log.error("Dropped event: device_id=%s  timestamp=%s",
                      event.get("device_id"), event.get("timestamp"))


# ── per-connection handler ────────────────────────────────────────────────────

def _handle_connection(conn: socket.socket, addr: tuple, producer: _ProducerWrapper) -> None:
    peer = f"{addr[0]}:{addr[1]}"
    log.info("New connection from %s", peer)
    buffer = ""
    try:
        conn.settimeout(120)  # 2-minute idle timeout
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                log.info("Connection closed by %s", peer)
                break

            buffer += chunk.decode("ascii", errors="replace")

            # Process complete lines (\\r\\n or \\n terminated)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                log.debug("Raw packet from %s: %r", peer, line[:120])

                event = _parse_packet(line)
                if event is None:
                    continue  # heartbeat / empty

                if "_parse_error" in event:
                    log.warning("Parse error for packet from %s — forwarding raw envelope", peer)

                log.info("Event: device=%s  lat=%.4f  lon=%.4f  speed=%.1f km/h  ts=%s",
                         event.get("device_id", "?"),
                         event.get("payload", {}).get("latitude", 0),
                         event.get("payload", {}).get("longitude", 0),
                         event.get("payload", {}).get("speed_kmh", 0),
                         event.get("timestamp", "?"))

                producer.send(event)

    except socket.timeout:
        log.warning("Connection from %s timed out (120s idle)", peer)
    except ConnectionResetError:
        log.info("Connection reset by %s", peer)
    except Exception as exc:
        log.error("Error handling connection from %s: %s", peer, exc, exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass
        log.info("Connection from %s closed.", peer)


# ── TCP server ────────────────────────────────────────────────────────────────

def run_server(host: str = HOST, port: int = PORT) -> None:
    producer = _ProducerWrapper()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(10)

    log.info("=" * 60)
    log.info("Mictrack MP91 TCP Listener")
    log.info("  Listening on  : %s:%d", host, port)
    log.info("  Kinesis stream: %s", os.environ.get("KINESIS_STREAM_NAME", "(from settings)"))
    log.info("  Region        : %s", os.environ.get("AWS_DEFAULT_REGION", "ca-central-1"))
    log.info("  Dry run       : %s", DRY_RUN)
    log.info("=" * 60)
    log.info("Device SMS setup:")
    log.info("  SERVER,1,<THIS_EC2_IP>,%d,0#", port)
    log.info("  TIMER,30#")
    log.info("  RESTART#")
    log.info("=" * 60)

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(
                target=_handle_connection,
                args=(conn, addr, producer),
                name=f"conn-{addr[0]}",
                daemon=True,
            )
            t.start()
    except KeyboardInterrupt:
        log.info("Shutting down listener...")
    finally:
        server.close()
        log.info("Listener stopped.")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_server()
