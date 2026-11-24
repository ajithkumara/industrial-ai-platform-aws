"""H02 / MP91 parser + gold tests. Packets are real captures from 2026-11-07."""
from edge.h02_parser import decode_status, parse_binary, parse_bronze_event, parse_text, split_frames
from edge.mp91_gold import build

TEXT = "*HQ,7018532019,V6,045237,A,4326.6568,N,07940.5269,W,000.00,000,071126,FFFFFBFF,302,00,55015,140168745,89882280666233645500#"
BIN_STORED = bytes.fromhex("24701853201904474807112643266562060794052886000000fbfffbff0003daa600000000012e00d6e7000002")
BIN_LIVE = bytes.fromhex("24701853201904515507112643266591060794052976000000fffffbff0003daa600000000012e00d6e7000004")


def test_text_frame():
    r = parse_text(TEXT)
    assert r["device_id"] == "7018532019"
    assert r["fix_time"] == "2026-11-07T04:52:37+00:00"
    assert abs(r["latitude"] - 43.44428) < 1e-4 and abs(r["longitude"] + 79.67545) < 1e-4
    assert r["iccid"].startswith("8988228066623364550") and r["mcc"] == "302"
    assert r["acc_on"] is False


def test_binary_frame_matches_vendor_doc():
    r = parse_binary(BIN_STORED)
    assert r["fix_time"] == "2026-11-07T04:47:48+00:00"
    assert r["gps_valid"] and r["latitude"] > 0 and r["longitude"] < 0  # N / W from flags nibble
    assert r["battery_pct"] == 100 and r["mileage_raw"] == 252582
    assert (r["mcc"], r["lac"], r["record_no"]) == ("302", "55015", 2)


def test_blind_spot_flag_distinguishes_stored_vs_live():
    assert parse_binary(BIN_STORED)["stored_data"] is True
    assert parse_binary(BIN_LIVE)["stored_data"] is False


def test_acc_bit_positive_logic():
    assert decode_status("FFFFFBFF")["acc_on"] is False
    assert decode_status("FFFFFFFF")["acc_on"] is True


def test_framing_and_rejects():
    frames, junk = split_frames(TEXT.encode() + BIN_LIVE + b"garbage")
    assert [k for k, _ in frames] == ["text", "binary"] and junk == b"garbage"
    recs, rej = parse_bronze_event({"event_id": "x", "raw_hex": b"TEST from laptop\r\n".hex()})
    assert recs == [] and len(rej) == 1


def test_record_id_is_deterministic():
    assert parse_binary(BIN_LIVE)["record_id"] == parse_binary(BIN_LIVE)["record_id"]


def _pt(t, acc, km, lat=43.44, lon=-79.67, spd=30.0):
    return {"record_id": t, "device_id": "7018532019", "fix_time": f"2026-11-07T{t}:00+00:00",
            "gps_valid": True, "latitude": lat, "longitude": lon, "speed_kmh": spd if acc else 0.0,
            "acc_on": acc, "mileage_raw": km}


def test_gold_trips_and_parking():
    pts = [_pt("10:00", False, 1000), _pt("10:10", True, 1000), _pt("10:20", True, 6000),
           _pt("10:30", False, 6000), _pt("11:00", True, 6000), _pt("11:05", True, 8000), _pt("11:10", False, 8000)]
    g = build(pts)
    assert g["totals"]["trips"] == 2 and g["totals"]["distance_km"] == 7.0
    p = g["parking"]
    assert p[0]["end"] == "2026-11-07T10:10:00+00:00"           # parked before first trip
    assert p[1]["duration_min"] == 40.0                          # 10:20 -> 11:00
    assert p[-1]["end"] is None                                  # still parked
