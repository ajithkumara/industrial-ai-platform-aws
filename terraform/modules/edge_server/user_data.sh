#!/bin/bash
# EC2 User Data — MP91 TCP listener (Amazon Linux 2023, arm64)
#
# Design rules (learned the hard way):
#   - ZERO package installs: no dnf, no pip. AL2023 ships python3 + AWS CLI v2.
#     The listener is stdlib-only and uploads via the `aws` CLI.
#   - Everything is mirrored to the serial console, so the bootstrap and the
#     listener can be read WITHOUT SSH or SSM:
#       aws ec2 get-console-output --instance-id <id> --latest --output text
#   - Raw bytes are captured as-is (bronze layer). No assumption that MP91
#     frames are newline-terminated — parse later in Athena/Spark.
#
# NOTE: this file is a Terraform templatefile. Only lake_bucket, region and
# tcp_port are substituted. Do not use dollar-brace syntax anywhere else.

exec > >(tee /var/log/user-data.log /dev/console) 2>&1
echo "=== IAP bootstrap start $(date -u) ==="
echo "python: $(python3 --version 2>&1)   aws: $(aws --version 2>&1)"

mkdir -p /opt/iap-edge /var/spool/iap-edge

cat > /opt/iap-edge/tcp_listener.py << 'PYEOF'
"""MP91 TCP listener — stdlib only.

Each recv() chunk becomes one JSON line in a local spool file. An uploader
thread ships closed spool files to S3 every FLUSH_SECONDS via the AWS CLI
(instance role credentials). If S3 is unreachable, files stay in the spool
and are retried — no data loss on transient failures.
"""
import json, os, socket, subprocess, threading, time, uuid
from datetime import datetime, timezone

BUCKET = os.environ["S3_BUCKET"]
REGION = os.environ.get("AWS_DEFAULT_REGION", "ca-central-1")
PORT = int(os.environ.get("TCP_PORT", "5013"))
SPOOL = "/var/spool/iap-edge"
FLUSH_SECONDS = int(os.environ.get("FLUSH_SECONDS", "60"))

lock = threading.Lock()
current = {"path": None, "fh": None, "opened": 0.0}


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


def rotate():
    with lock:
        if current["fh"] is not None:
            current["fh"].close()
            os.rename(current["path"], current["path"][:-5])  # drop .part
            current.update(path=None, fh=None, opened=0.0)


def uploader():
    while True:
        time.sleep(FLUSH_SECONDS)
        try:
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
        except Exception as e:  # never let the uploader die
            log(f"uploader error: {e}")


def send_acks(conn, data, peer):
    """Reply R12 per the Mictrack MP91 protocol doc (section 4.1):
    *HQ,<device_id>,R12,<hhmmss>#  — confirms receipt of *HQ and $ records."""
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
            log(f"rx {len(data)}B from {peer}: {data[:80]!r}")
            send_acks(conn, data, peer)
    except Exception as e:
        log(f"conn error {peer}: {e}")
    finally:
        conn.close()
        log(f"disconnect {peer}")


threading.Thread(target=uploader, daemon=True).start()
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", PORT))
srv.listen(16)
log(f"listening on 0.0.0.0:{PORT} -> s3://{BUCKET}/raw/mp91/ (flush {FLUSH_SECONDS}s)")
while True:
    c, a = srv.accept()
    threading.Thread(target=handle, args=(c, a), daemon=True).start()
PYEOF

cat > /opt/iap-edge/.env << EOF
S3_BUCKET=${lake_bucket}
AWS_DEFAULT_REGION=${region}
TCP_PORT=${tcp_port}
FLUSH_SECONDS=60
EOF

cat > /etc/systemd/system/iap-edge.service << 'EOF'
[Unit]
Description=IAP MP91 TCP Listener
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/iap-edge
EnvironmentFile=/opt/iap-edge/.env
ExecStart=/usr/bin/python3 -u /opt/iap-edge/tcp_listener.py
Restart=always
RestartSec=5
StandardOutput=journal+console
StandardError=journal+console
SyslogIdentifier=iap-edge

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now iap-edge
sleep 3
systemctl is-active iap-edge && echo "iap-edge ACTIVE" || echo "iap-edge NOT ACTIVE"
ss -ltnp | grep ":${tcp_port}" || echo "port ${tcp_port} NOT listening"
echo "=== IAP bootstrap complete $(date -u) ==="
