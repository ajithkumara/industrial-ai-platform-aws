"""H02 protocol parser for the Mictrack MP91 (stdlib only — runs in Lambda as-is).

The MP91 speaks H02 (a.k.a. "HQ" protocol) and sends two frame types over
the same TCP connection, observed in our bronze data on 2026-11-07:

1. Text frame (ASCII), one per connection, terminated by '#':
     *HQ,7018532019,V6,045151,A,4326.6589,N,07940.5293,W,000.05,000,071126,
     FFFFFBFF,302,00,55015,140168745,89882280666233645500#
   fields: id, cmd, hhmmss, validity, lat(DDMM.MMMM), N/S, lon(DDDMM.MMMM),
           E/W, speed(knots), course, ddmmyy, status(hex), MCC, MNC, LAC,
           CellID, ICCID (V6 adds the ICCID)

2. Binary frame, 45 bytes, starting with '$' (0x24), BCD encoded:
     off len  field
       0   1  '$'
       1   5  device id (10 BCD digits)
       6   3  hhmmss
       9   3  ddmmyy
      12   4  latitude  DD MM.MMMM            (8 BCD digits)
      16   1  battery/aux byte (raw — meaning unconfirmed)
      17   5  longitude DDD MM.MMMM + flags nibble (9 digits + 1 nibble)
              flags: 0x2 = GPS valid, 0x4 = North, 0x8 = East
      22   3  speed (3 BCD digits, knots) + course (3 BCD digits)
      25   4  status (32 bits, same as text frame)
      29   4  mileage (uint32; unit not stated in the vendor doc)
      33   4  reserved
      37   2  MCC   39 1 MNC   40 2 LAC   42 2 cell id   44 1 record number

Source: "Mictrack Communication Protocol For MP91" (vendor PDF). Battery byte:
06=100%, 05=80%, 04=60%, 03=20%, 02=10%, 01=5%, 00=0%.

Status (4 bytes, NEGATIVE logic: bit=0 means active, except ACC):
  byte1 bit1 towed alarm, bit2 blind-spot (stored/buffered) data,
        bit3 fuel/power cut, bit4 battery-removal alarm
  byte2 bit1 shake alarm, bit3 external power disconnected
  byte3 bit0 door open, bit1 fence, bit2 ACC (1 = ON, 0 = OFF — positive)
  byte4 bit1 SOS, bit2 over-speed, bit3 unauthorized ignition,
        bit4 unauthorized door, bit5 vehicle battery low, bit6 backup battery low

Coordinates and speeds were cross-checked: the text and binary frames from the
same connection decode to the same position within GPS jitter (< 5 m).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

KNOTS_TO_KMH = 1.852
BINARY_FRAME_LEN = 45


class H02ParseError(ValueError):
    pass


# ── helpers ──────────────────────────────────────────────────────────────────

def _ts(hhmmss: str, ddmmyy: str) -> str:
    try:
        dt = datetime.strptime(ddmmyy + hhmmss, "%d%m%y%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise H02ParseError(f"bad timestamp {ddmmyy} {hhmmss}") from e
    return dt.isoformat()


def _record_id(device_id: str, fix_time: str, frame_type: str, lat: float, lon: float) -> str:
    # Deterministic: re-processing the same raw file yields the same ids (idempotent silver).
    key = f"{device_id}|{fix_time}|{frame_type}|{lat:.6f}|{lon:.6f}"
    return hashlib.sha1(key.encode()).hexdigest()[:20]


def _base(device_id, fix_time, valid, lat, lon, speed_knots, course, status_hex, frame_type):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise H02ParseError(f"coordinates out of range {lat},{lon}")
    rec = {
        "record_id": _record_id(device_id, fix_time, frame_type, lat, lon),
        "device_id": device_id,
        "fix_time": fix_time,
        "gps_valid": valid,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "speed_kmh": round(speed_knots * KNOTS_TO_KMH, 2),
        "course_deg": course,
        "status_hex": status_hex,
        "frame_type": frame_type,
    }
    rec.update(decode_status(status_hex))
    return rec


BATTERY_PCT = {6: 100, 5: 80, 4: 60, 3: 20, 2: 10, 1: 5, 0: 0}

# (byte index 0-3, bit, name) — negative logic flags
_NEG_FLAGS = [
    (0, 1, "alarm_towed"), (0, 2, "stored_data"), (0, 3, "fuel_power_cut"),
    (0, 4, "alarm_battery_removed"), (1, 1, "alarm_shake"),
    (1, 3, "external_power_disconnected"), (2, 0, "door_open"),
    (2, 1, "alarm_fence"), (3, 1, "alarm_sos"), (3, 2, "alarm_overspeed"),
    (3, 3, "alarm_unauthorized_ignition"), (3, 4, "alarm_unauthorized_door"),
    (3, 5, "vehicle_battery_low"), (3, 6, "backup_battery_low"),
]


def decode_status(status_hex: str) -> dict:
    b = bytes.fromhex(status_hex)
    out = {name: not (b[i] >> bit) & 1 for i, bit, name in _NEG_FLAGS}
    out["acc_on"] = bool((b[2] >> 2) & 1)  # ACC is positive logic per vendor doc
    return out


def ack_frame(device_id: str, hhmmss: str) -> bytes:
    """R12 server confirmation the device expects after *HQ / $ uplinks."""
    return f"*HQ,{device_id},R12,{hhmmss}#".encode()


# ── text frame ───────────────────────────────────────────────────────────────

def parse_text(frame: str) -> dict:
    """Parse one '*HQ,...#' frame."""
    body = frame.strip()
    if not (body.startswith("*HQ,") and body.endswith("#")):
        raise H02ParseError("not an H02 text frame")
    f = body[1:-1].split(",")
    if len(f) < 13:
        raise H02ParseError(f"too few fields ({len(f)})")
    _, device_id, cmd, hhmmss, validity, lat_s, ns, lon_s, ew, spd, crs, ddmmyy, status = f[:13]
    if cmd not in ("V1", "V6", "V4", "V5"):
        raise H02ParseError(f"unsupported command {cmd}")
    try:
        lat = int(lat_s[:2]) + float(lat_s[2:]) / 60
        lon = int(lon_s[:3]) + float(lon_s[3:]) / 60
        speed = float(spd)
        course = int(float(crs))
    except ValueError as e:
        raise H02ParseError(f"bad numeric field: {e}") from e
    if ns == "S":
        lat = -lat
    if ew == "W":
        lon = -lon
    rec = _base(device_id, _ts(hhmmss, ddmmyy), validity == "A", lat, lon, speed, course, status.upper(), "text_" + cmd)
    extra = f[13:]
    if len(extra) >= 4:
        rec.update(mcc=extra[0], mnc=extra[1], lac=extra[2], cell_id=extra[3])
    if cmd == "V6" and len(extra) >= 5:
        rec["iccid"] = extra[4]
    return rec


# ── binary frame ─────────────────────────────────────────────────────────────

def parse_binary(frame: bytes) -> dict:
    """Parse one 45-byte '$' frame."""
    if len(frame) != BINARY_FRAME_LEN or frame[0] != 0x24:
        raise H02ParseError(f"not a {BINARY_FRAME_LEN}-byte H02 binary frame")
    h = frame.hex()  # BCD → digits; each byte is two hex chars
    if not (h[2:43] + h[44:50]).isdigit():  # BCD region (id..course, minus flags nibble)
        raise H02ParseError("non-BCD digits in binary frame")
    device_id = h[2:12]
    hhmmss, ddmmyy = h[12:18], h[18:24]
    lat = int(h[24:26]) + int(h[26:32]) / 10000 / 60
    battery_raw = frame[16]
    lon_digits = h[34:43]  # 9 BCD digits: DDD MM MMMM
    lon = int(lon_digits[:3]) + int(lon_digits[3:]) / 10000 / 60
    flags = int(h[43], 16)
    if not flags & 0x4:
        lat = -lat
    if not flags & 0x8:
        lon = -lon
    speed = int(h[44:47])
    course = int(h[47:50])
    status = h[50:58].upper()
    rec = _base(device_id, _ts(hhmmss, ddmmyy), bool(flags & 0x2), lat, lon, speed, course, status, "binary")
    rec["battery_pct"] = BATTERY_PCT.get(battery_raw)
    rec["mileage_raw"] = int(h[58:66], 16)
    rec.update(
        mcc=str(int(h[74:78], 16)), mnc=f"{int(h[78:80], 16):02d}",
        lac=str(int(h[80:84], 16)), cell_id=str(int(h[84:88], 16)),
        record_no=int(h[88:90], 16),
    )
    return rec


# ── framing ──────────────────────────────────────────────────────────────────

def split_frames(data: bytes) -> tuple[list[tuple[str, bytes]], bytes]:
    """Split a byte chunk into ('text'|'binary', frame) tuples.

    Returns (frames, leftover). Leftover is unrecognised bytes — the caller
    quarantines it rather than silently dropping it.
    """
    frames, junk, i = [], bytearray(), 0
    while i < len(data):
        b = data[i]
        if b == 0x2A:  # '*'
            end = data.find(b"#", i)
            if end == -1:
                junk += data[i:]
                break
            frames.append(("text", data[i:end + 1]))
            i = end + 1
        elif b == 0x24 and len(data) - i >= BINARY_FRAME_LEN:  # '$'
            frames.append(("binary", data[i:i + BINARY_FRAME_LEN]))
            i += BINARY_FRAME_LEN
        elif b in (0x0D, 0x0A):
            i += 1
        else:
            junk.append(b)
            i += 1
    return frames, bytes(junk)


def parse_bronze_event(event: dict) -> tuple[list[dict], list[dict]]:
    """Parse one bronze JSONL event (as written by the edge listener).

    Returns (records, rejects). Each record carries lineage back to bronze.
    """
    lineage = {
        "bronze_event_id": event.get("event_id"),
        "received_at": event.get("received_at"),
        "peer": event.get("peer"),
    }
    try:
        data = bytes.fromhex(event["raw_hex"])
    except (KeyError, ValueError) as e:
        return [], [{**lineage, "reason": f"bad raw_hex: {e}", "raw_hex": event.get("raw_hex")}]

    records, rejects = [], []
    frames, junk = split_frames(data)
    for kind, frame in frames:
        try:
            rec = parse_text(frame.decode("ascii")) if kind == "text" else parse_binary(frame)
            records.append({**rec, **lineage})
        except (H02ParseError, UnicodeDecodeError) as e:
            rejects.append({**lineage, "reason": str(e), "raw_hex": frame.hex()})
    if junk:
        rejects.append({**lineage, "reason": "unrecognised bytes", "raw_hex": junk.hex()})
    return records, rejects
