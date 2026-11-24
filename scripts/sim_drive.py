"""Synthetic drive for FleetPilot — replays a real past trip as a SEPARATE simulated device ("Test Van").

Your real car (device 7018532019) is never touched. The script:
  1. registers a simulated vehicle (device 9000000001, vehicle "sim1") in your account,
  2. sends one parked packet, waits so the vehicle shows up in the app (Test Van),
  3. replays the chosen trip over TCP to the real edge listener, one H02 packet per second.
That exercises the full path: listener -> S3 -> live DynamoDB write -> /live -> Live Map.

Usage (PowerShell, from the repo root, AWS_PROFILE=iap-dev):
  python scripts/sim_drive.py                 # register, park, wait, drive the most recent trip
  python scripts/sim_drive.py --speed 4       # replay 4x faster (default is real time: a 28 min trip takes 28 min)
  python scripts/sim_drive.py --lead 0        # skip the wait (Test Van already visible in the app)
  python scripts/sim_drive.py --dry-run       # print frames only, send nothing, change nothing
  python scripts/sim_drive.py --cleanup       # remove the simulated vehicle/device registration

Open the Live Fleet Map and select "Test Van (simulated)" before the drive phase starts.
The trip is replayed on its real timestamps (one packet per second), so a 28 min trip takes 28 min. Ctrl+C stops it.
"""
import argparse
import json
import math
import socket
import sys
import time
from datetime import datetime, timezone

REGION = "ca-central-1"
TABLE = "iap-dev-fleet"
BUCKET = "iap-dev-lake-313092058964"
HOST, PORT = "15.175.32.126", 5013
REAL_DEVICE = "7018532019"          # only READ, to find your account
SIM_DEVICE, SIM_VEHICLE, SIM_NAME = "9000000001", "sim1", "Test Van (simulated)"
STATUS_ACC_ON = "FFFFFFFF"          # no alarms, ACC on (negative-logic bits all set)
STATUS_ACC_OFF = "FFFFFBFF"


def aws():
    import boto3
    return boto3.resource("dynamodb", region_name=REGION).Table(TABLE), boto3.client("s3", region_name=REGION)


def find_account(ddb):
    it = ddb.get_item(Key={"PK": f"DEVICE#{REAL_DEVICE}", "SK": "META"}).get("Item")
    if not it:
        raise SystemExit(f"device {REAL_DEVICE} is not registered; cannot find your account")
    return it["account_id"]


def register(ddb, account):
    ddb.put_item(Item={"PK": f"ACCOUNT#{account}", "SK": f"VEHICLE#{SIM_VEHICLE}", "name": SIM_NAME, "device_id": SIM_DEVICE})
    ddb.put_item(Item={"PK": f"DEVICE#{SIM_DEVICE}", "SK": "META", "account_id": account, "vehicle_id": SIM_VEHICLE})
    print(f"registered {SIM_NAME}: device {SIM_DEVICE} -> account {account}")


def cleanup():
    ddb, _ = aws()
    account = find_account(ddb)
    for k in ({"PK": f"ACCOUNT#{account}", "SK": f"VEHICLE#{SIM_VEHICLE}"}, {"PK": f"DEVICE#{SIM_DEVICE}", "SK": "META"},
              {"PK": f"DEVICE#{SIM_DEVICE}", "SK": "WATCH"}, {"PK": f"DEVICE#{SIM_DEVICE}", "SK": "LIVE"}):
        ddb.delete_item(Key=k)
    print("simulated vehicle and device removed (refresh the app; it disappears after the next gold rebuild, about 1 min)")


def load_trip(gold, which):
    vehicles = [v for v in gold["vehicles"] if v["device_id"] == REAL_DEVICE] or gold["vehicles"]
    trips = [t for v in vehicles for t in v["trips"] if len(t["points"]) >= 2]
    if not trips:
        raise SystemExit("no trip with points found in gold data")
    trips.sort(key=lambda t: t["start"])
    t = trips[-1] if which == "last" else trips[int(which)]
    print(f"replaying trip {t['start']} -> {t['end']}  {t['distance_km']} km  {len(t['points'])} points")
    return t["points"]


def _t(p):
    return datetime.fromisoformat(p[3].replace("Z", "+00:00")).timestamp()


def resample(points, step, speed=1.0):
    """(lat, lon, kmh) samples every `step` seconds of REAL trip time / speed, interpolated on the recorded timestamps."""
    ts = [_t(p) for p in points]
    out, t, j = [], ts[0], 0
    while t <= ts[-1]:
        while j < len(points) - 2 and ts[j + 1] < t:
            j += 1
        span = (ts[j + 1] - ts[j]) or 1
        f = min(max((t - ts[j]) / span, 0), 1)
        a, b = points[j], points[j + 1]
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f))
        t += step * speed
    return out


def bearing(a, b):
    la1, la2, dlo = math.radians(a[0]), math.radians(b[0]), math.radians(b[1] - a[1])
    y = math.sin(dlo) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlo)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def frame(lat, lon, kmh, course, acc_on, now=None):
    now = now or datetime.now(timezone.utc)
    la, lo = abs(lat), abs(lon)
    lat_s = f"{int(la):02d}{(la - int(la)) * 60:07.4f}"
    lon_s = f"{int(lo):03d}{(lo - int(lo)) * 60:07.4f}"
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    return (f"*HQ,{SIM_DEVICE},V1,{now:%H%M%S},A,{lat_s},{ns},{lon_s},{ew},{kmh / 1.852:.2f},{course:.0f},"
            f"{now:%d%m%y},{STATUS_ACC_ON if acc_on else STATUS_ACC_OFF},302,720,1234,5678#")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--speed", type=float, default=1.0, help="replay speed: 1 = real time (default), 4 = four times faster")
    p.add_argument("--lead", type=int, default=100, help="seconds to wait after the parked packet so Test Van appears in the app")
    p.add_argument("--trip", default="last", help="'last' or an index into the trips sorted by start time")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--host", default=HOST)
    p.add_argument("--gold-file", help="read gold JSON from a local file instead of S3 (testing)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--cleanup", action="store_true")
    a = p.parse_args()

    if a.cleanup:
        return cleanup()

    if a.gold_file:
        gold = json.load(open(a.gold_file))
        ddb = account = None
    else:
        ddb, s3 = aws()
        account = find_account(ddb)
        gold = json.loads(s3.get_object(Bucket=BUCKET, Key=f"gold/accounts/{account}/latest.json")["Body"].read())
    samples = resample(load_trip(gold, a.trip), a.interval, a.speed)
    print(f"{len(samples)} packets, about {len(samples) * a.interval / 60:.1f} min")

    if a.dry_run:
        for i, s in enumerate(samples[:5]):
            print(frame(s[0], s[1], s[2], bearing(s, samples[min(i + 1, len(samples) - 1)]), True))
        print(f"... {len(samples)} packets in total; nothing sent")
        return

    register(ddb, account)
    sock = socket.create_connection((a.host, PORT), timeout=10)
    sock.settimeout(0.2)

    def send(fr):
        sock.sendall(fr.encode())
        try:
            sock.recv(256)  # R12 ack; ignored
        except socket.timeout:
            pass

    s0 = samples[0]
    send(frame(s0[0], s0[1], 0, 0, False))
    print("parked packet sent")
    if a.lead:
        print(f"Open the Live Fleet Map now and select '{SIM_NAME}' once it appears (about 1-2 min).")
        for left in range(a.lead, 0, -10):
            print(f"  drive starts in {left}s", flush=True)
            send(frame(s0[0], s0[1], 0, 0, False))  # keep the connection alive
            time.sleep(10)
    print("driving...")
    t0 = time.time()
    for i, s in enumerate(samples):
        nxt = samples[min(i + 1, len(samples) - 1)]
        send(frame(s[0], s[1], s[2], bearing(s, nxt), True))
        if i % 30 == 0:
            print(f"  packet {i + 1}/{len(samples)}  {s[0]:.4f},{s[1]:.4f}  {s[2]:.0f} km/h", flush=True)
        time.sleep(max(0, t0 + (i + 1) * a.interval - time.time()))
    last = samples[-1]
    send(frame(last[0], last[1], 0, 0, False))
    sock.close()
    print("done: parked at the end of the trip. Run with --cleanup when finished testing.")


if __name__ == "__main__":
    sys.exit(main())
