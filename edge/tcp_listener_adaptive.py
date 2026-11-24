"""MP91 TCP listener, adaptive upload version (stdlib only).

Same behaviour as the listener embedded in terraform/modules/edge_server/user_data.sh, plus:
  * the uploader ships spool files every FAST_SECONDS (default 10) while the car is moving
    and every SLOW_SECONDS (default 60) otherwise;
  * "moving" = any position report with speed above MOVING_KNOTS in the last MOVING_HOLD seconds.
Files only exist when the tracker sent data, so a parked car costs almost nothing.

Durability (Phase 2): every chunk is fsync'ed to the disk spool BEFORE the R12 ack is sent, so a
crash, reboot or EC2 recovery never loses a record the tracker believes was delivered (no ack =
the tracker keeps it and resends). On startup, spool files left half-written by a crash
(*.jsonl.part) are closed out and uploaded like any other file.
Install on the running server without replacing it: see docs (SSM steps in chat / runbook).
"""
import json, os, socket, subprocess, threading, time, uuid
from datetime import datetime, timezone

BUCKET = os.environ.get("S3_BUCKET", "")
REGION = os.environ.get("AWS_DEFAULT_REGION", "ca-central-1")
PORT = int(os.environ.get("TCP_PORT", "5013"))
SPOOL = os.environ.get("SPOOL_DIR", "/var/spool/iap-edge")
FAST_SECONDS = int(os.environ.get("FAST_SECONDS", "10"))
SLOW_SECONDS = int(os.environ.get("FLUSH_SECONDS", "60"))
MOVING_KNOTS = float(os.environ.get("MOVING_KNOTS", "1.0"))   # ~1.9 km/h
MOVING_HOLD = int(os.environ.get("MOVING_HOLD", "90"))        # keep fast mode this long after last movement

lock = threading.Lock()
current = {"path": None, "fh": None, "opened": 0.0}
moving_until = {"t": 0.0}

# Hot path (optional): latest position -> DynamoDB while moving AND watched. Off unless FLEET_TABLE is set.
live = None
if os.environ.get("FLEET_TABLE"):
    try:
        from live_push import LivePublisher
        from h02_parser import parse_text, parse_binary, split_frames
        live = LivePublisher(os.environ["FLEET_TABLE"], REGION, log=lambda m: print(f"[iap-edge] {m}", flush=True))
        live.start()
    except Exception as e:  # the S3 path must keep working whatever happens here
        print(f"[iap-edge] live path disabled: {e}", flush=True)


def offer_live(data):
    try:
        frames, _ = split_frames(data)
        for kind, frame in frames:
            try:
                live.offer(parse_text(frame.decode("ascii")) if kind == "text" else parse_binary(frame))
            except Exception:
                pass
    except Exception:
        pass


def log(msg):
    print(f"[iap-edge] {datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def write_event(evt):
    with lock:
        if current["fh"] is None:
            name = f"mp91_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}.jsonl.part"
            current["path"] = os.path.join(SPOOL, name)
            current["fh"] = open(current["path"], "a")
            current["opened"] = time.time()
        current["fh"].write(json.dumps(evt) + "\n")
        current["fh"].flush()
        os.fsync(current["fh"].fileno())  # on disk before we ack the tracker


def rotate():
    with lock:
        if current["fh"] is not None:
            current["fh"].close()
            os.rename(current["path"], current["path"][:-5])  # drop .part
            current.update(path=None, fh=None, opened=0.0)


def recover_orphans():
    """Close out spool files a crash left as *.part so the uploader ships them. Returns how many."""
    n = 0
    for name in os.listdir(SPOOL):
        if name.endswith(".jsonl.part"):
            src = os.path.join(SPOOL, name)
            if os.path.getsize(src) == 0:
                os.remove(src)
                continue
            os.rename(src, src[:-5])
            n += 1
    return n


def max_speed_knots(data):
    """Highest speed (knots) in the position reports inside one recv() chunk; 0 if none."""
    best, i = 0.0, 0
    try:
        while i < len(data):
            if data[i] == 0x2A:  # text frame *HQ,id,cmd,hhmmss,A,lat,N,lon,W,speed,...#
                end = data.find(b"#", i)
                if end == -1:
                    break
                f = data[i:end].decode("ascii", "replace").split(",")
                if len(f) > 9 and f[0] == "*HQ":
                    try:
                        best = max(best, float(f[9]))
                    except ValueError:
                        pass
                i = end + 1
            elif data[i] == 0x24 and len(data) - i >= 45:  # binary frame: speed = 3 BCD digits at byte 22
                h = data[i:i + 45].hex()
                try:
                    best = max(best, float(int(h[44:47])))
                except ValueError:
                    pass
                i += 45
            else:
                i += 1
    except Exception:
        pass
    return best


def upload_spool():
    rotate()
    for name in sorted(os.listdir(SPOOL)):
        if not name.endswith(".jsonl"):
            continue
        ts = name.split("_")[1]  # YYYYMMDDTHHMMSSZ
        key = f"raw/mp91/year={ts[0:4]}/month={ts[4:6]}/day={ts[6:8]}/{name}"
        src = os.path.join(SPOOL, name)
        r = subprocess.run(
            ["aws", "s3", "cp", src, f"s3://{BUCKET}/{key}", "--region", REGION, "--only-show-errors"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            os.remove(src)
            log(f"uploaded s3://{BUCKET}/{key}")
        else:
            log(f"upload FAILED (will retry) {name}: {r.stderr.strip()}")


def uploader():
    last = time.time()
    while True:
        time.sleep(1)
        interval = FAST_SECONDS if time.time() < moving_until["t"] else SLOW_SECONDS
        if time.time() - last < interval:
            continue
        last = time.time()
        try:
            upload_spool()
        except Exception as e:  # never let the uploader die
            log(f"uploader error: {e}")


def send_acks(conn, data, peer):
    """Reply R12 per the Mictrack MP91 protocol doc (section 4.1):
    *HQ,<device_id>,R12,<hhmmss>#  - confirms receipt of *HQ and $ records."""
    acks = []
    try:
        i = 0
        while i < len(data):
            if data[i] == 0x2A:  # '*HQ,id,cmd,hhmmss,...#'
                end = data.find(b"#", i)
                if end == -1:
                    break
                f = data[i:end].decode("ascii", "replace").split(",")
                if len(f) > 3 and f[0] == "*HQ":
                    acks.append((f[1], f[3]))
                i = end + 1
            elif data[i] == 0x24 and len(data) - i >= 45:  # '$' binary record
                h = data[i:i + 45].hex()
                acks.append((h[2:12], h[12:18]))
                i += 45
            else:
                i += 1
        for dev, t in acks:
            conn.sendall(f"*HQ,{dev},R12,{t}#".encode())
            log(f"ack R12 {dev} {t} -> {peer}")
    except Exception as e:
        log(f"ack error {peer}: {e}")


def handle(conn, addr):
    peer = f"{addr[0]}:{addr[1]}"
    log(f"connect {peer}")
    try:
        conn.settimeout(600)  # trackers send heartbeats; drop dead sockets after 10 min
        while True:
            data = conn.recv(4096)
            if not data:
                break
            write_event({
                "event_id": str(uuid.uuid4()),
                "received_at": datetime.now(timezone.utc).isoformat(),
                "source": "mp91_tcp",
                "peer": peer,
                "raw_ascii": data.decode("ascii", errors="replace"),
                "raw_hex": data.hex(),
                "bytes": len(data),
            })
            if max_speed_knots(data) > MOVING_KNOTS:
                moving_until["t"] = time.time() + MOVING_HOLD
            if live is not None:
                offer_live(data)
            log(f"rx {len(data)}B from {peer}: {data[:80]!r}")
            send_acks(conn, data, peer)
    except Exception as e:
        log(f"conn error {peer}: {e}")
    finally:
        conn.close()
        log(f"disconnect {peer}")


def main():
    if not BUCKET:
        raise SystemExit("S3_BUCKET is not set")
    os.makedirs(SPOOL, exist_ok=True)
    n = recover_orphans()
    pending = len([f for f in os.listdir(SPOOL) if f.endswith(".jsonl")])
    log(f"spool {SPOOL}: recovered {n} interrupted file(s), {pending} file(s) waiting to upload")
    threading.Thread(target=uploader, daemon=True).start()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(16)
    log(f"listening on 0.0.0.0:{PORT} -> s3://{BUCKET}/raw/mp91/ (fast {FAST_SECONDS}s while moving, else {SLOW_SECONDS}s); live path {'ON' if live else 'off'}")
    while True:
        c, a = srv.accept()
        threading.Thread(target=handle, args=(c, a), daemon=True).start()


if __name__ == "__main__":
    main()
