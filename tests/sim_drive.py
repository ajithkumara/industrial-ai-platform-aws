"""Synthetic drive for FleetPilot — replays a real past trip as a SEPARATE simulated device ("Test Van").

Your real car (device 7018532019) is never touched. The script:
  1. registers a simulated vehicle (device 9000000001, vehicle "sim1") in your account,
  2. sends one parked packet, waits so the vehicle shows up in the app (Test Van),
  3. replays the chosen trip over TCP to the real edge listener, one H02 packet per second.
That exercises the full path: listener -> S3 -> live DynamoDB write -> /live -> Live Map.

Usage (PowerShell, from the repo root, AWS_PROFILE=iap-dev):
  python scripts/sim_drive.py                 # register, park, wait, drive the most recent trip
  python scripts/sim_drive.py --packets 120   # longer drive (default 90 packets = about 90 s)
  python scripts/sim_drive.py --lead 0        # skip the wait (Test Van already visible in the app)
  python scripts/sim_drive.py --dry-run       # print frames only, send nothing, change nothing
  python scripts/sim_drive.py --cleanup       # remove the simulated vehicle/device registration

Open the Live Fleet Map and select "Test Van (simulated)" before the drive phase starts.
The trip is compressed (a 28 min trip is replayed in about 90 s), so the dot moves fast; that is expected.
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


def resample(points, n):
    """n evenly spaced (lat, lon, kmh) samples along the recorded points (linear interpolation)."""
    out = []
    for i in range(n):
        x = i * (len(points) - 1) / max(n - 1, 1)
        a = int(x)
        b = min(a + 1, len(points) - 1)
        f = x - a
        lat = points[a][0] + (points[b][0] - points[a][0]) * f
        lon = points[a][1] + (points[b][1] - points[a][1]) * f
        kmh = points[a][2] + (points[b][2] - points[a][2]) * f
        out.append((lat, lon, kmh))
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
    p.add_argument("--packets", type=int, default=90)
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
    samples = resample(load_trip(gold, a.trip), a.packets)

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
        send(frame(s[0], s[1], max(s[2], 20.0), bearing(s, nxt), True))
        if i % 10 == 0:
            print(f"  packet {i + 1}/{len(samples)}  {s[0]:.4f},{s[1]:.4f}  {max(s[2], 20.0):.0f} km/h", flush=True)
        time.sleep(max(0, t0 + (i + 1) * a.interval - time.time()))
    last = samples[-1]
    send(frame(last[0], last[1], 0, 0, False))
    sock.close()
    print("done: parked at the end of the trip. Run with --cleanup when finished testing.")


if __name__ == "__main__":
    sys.exit(main())
