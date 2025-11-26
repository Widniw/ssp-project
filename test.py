#!/usr/bin/python3
import argparse
import json
import random
import re
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

from mininet.log import setLogLevel, info, warn
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.link import TCLink

from geant_topology import Geant

# --- Optional SciPy (used only to sample distributions for flow schedule) ---
SCIPY_OK = False


@dataclass
class FlowSpec:
    flow_id: int
    traffic_class: str          # "voip" / "video" / "bulk" / "interactive"
    src: str                    # host name, e.g., "h1"
    dst: str                    # host name, e.g., "h22"
    start_s: float              # relative start time (seconds from experiment start)
    duration_s: int
    proto: str                  # "udp" or "tcp"
    rate_bps: Optional[int]     # UDP target rate; TCP bulk uses None
    pkt_bytes: Optional[int]    # for UDP
    tos_hex: str                # iperf2 "-S" expects integer/hex TOS


# @dataclass
# class FlowResult:
#     flow: FlowSpec
#     iperf_raw: str
#     ping_raw: str
#     parsed: Dict


def pick_random_pairs(host_names: List[str], n_pairs: int, seed: Optional[int] = None) -> List[Tuple[str, str]]:
    """
    Draw random (src, dst) pairs, avoiding src == dst.
    Duplicates may happen if n_pairs is large; that's often fine for traffic mixes.
    """
    rng = random.Random(seed)
    pairs = []
    for _ in range(n_pairs):
        src = rng.choice(host_names)
        dst = rng.choice(host_names)
        while dst == src:
            dst = rng.choice(host_names)
        pairs.append((src, dst))
    return pairs


def _sample_exponential(mean_s: float) -> float:
    if SCIPY_OK:
        return float(expon(scale=mean_s).rvs())
    # fallback: classic inverse transform (no NumPy needed)
    u = random.random()
    return -mean_s * (0.0 if u == 0.0 else (math.log(u)))


def _sample_lognormal(mean: float, sigma: float) -> float:
    """
    SciPy lognorm parameterization is by sigma (s) and scale=exp(mu).
    Here we treat 'mean' as scale and 'sigma' as shape-ish for convenience.
    """
    if SCIPY_OK:
        return float(lognorm(s=sigma, scale=mean).rvs())
    # fallback: rough approx without SciPy
    return mean * (1.0 + sigma * (random.random() - 0.5))


def generate_flow_schedule(
    host_names: List[str],
    n_flows: int,
    seed: int,
    arrival_mean_s: float,
    experiment_duration_s: int
) -> List[FlowSpec]:
    """
    Create a mixed traffic schedule. SciPy is used (if available) to sample:
      - inter-arrival times (exponential)
      - VBR-like rates/durations (lognormal)
    """
    rng = random.Random(seed)

    # Traffic class mix (edit as you like)
    classes = ["voip", "video", "bulk", "interactive"]
    weights = [0.35, 0.25, 0.25, 0.15]

    # DSCP/TOS suggestions (TOS = DSCP<<2)
    # - VoIP: EF (46) => 46<<2 = 184 = 0xb8
    # - Video: AF41 (34) => 34<<2 = 136 = 0x88
    # - Bulk/Interactive: BE (0) => 0x00
    tos_map = {
        "voip": "0xb8",
        "video": "0x88",
        "bulk": "0x00",
        "interactive": "0x00",
    }

    pairs = pick_random_pairs(host_names, n_flows, seed=seed + 1000)

    flows: List[FlowSpec] = []
    t = 0.0

    for i in range(n_flows):
        # Inter-arrival time
        if SCIPY_OK:
            delta = float(expon(scale=arrival_mean_s).rvs(random_state=rng.randint(1, 10**9)))
        else:
            # simple exponential without SciPy
            u = rng.random()
            delta = -arrival_mean_s * (0.0 if u == 0.0 else __import__("math").log(u))

        t += delta
        if t >= experiment_duration_s:
            break

        traffic_class = rng.choices(classes, weights=weights, k=1)[0]
        src, dst = pairs[i]

        if traffic_class == "voip":
            proto = "udp"
            duration = int(rng.randint(10, 30))
            # VoIP-like: small packets, constant-ish rate (e.g., 64 kbps)
            rate_bps = 64_000
            pkt_bytes = 160  # ~20ms voice payload vibe; tweak as needed

        elif traffic_class == "video":
            proto = "udp"
            duration = int(rng.randint(15, 60))
            # VBR-like: sample around few Mbps
            if SCIPY_OK:
                r_mbps = float(lognorm(s=0.5, scale=3.0).rvs(random_state=rng.randint(1, 10**9)))
            else:
                r_mbps = 2.0 + 4.0 * rng.random()
            r_mbps = max(0.5, min(r_mbps, 15.0))
            rate_bps = int(r_mbps * 1_000_000)
            pkt_bytes = 1200

        elif traffic_class == "bulk":
            proto = "tcp"
            duration = int(rng.randint(20, 90))
            rate_bps = None
            pkt_bytes = None

        else:  # "interactive"
            proto = "tcp"
            duration = int(rng.randint(3, 15))
            rate_bps = None
            pkt_bytes = None

        flows.append(
            FlowSpec(
                flow_id=i + 1,
                traffic_class=traffic_class,
                src=src,
                dst=dst,
                start_s=round(t, 3),
                duration_s=duration,
                proto=proto,
                rate_bps=rate_bps,
                pkt_bytes=pkt_bytes,
                tos_hex=tos_map[traffic_class],
            )
        )

    return flows


def start_iperf_servers(net: Mininet, base_port: int) -> None:
    """
    Start one iperf2 server per host on a deterministic port.
    """
    info("* Starting iperf servers on all hosts\n")
    for h in net.hosts:
        idx = int(h.name[1:])  # "h12" -> 12
        port = base_port + idx
        # best-effort cleanup
        h.cmd('pkill -f "iperf -s" >/dev/null 2>&1 || true')
        h.cmd(f"iperf -s -p {port} -D")  # -D = daemon
    time.sleep(0.5)


def parse_ping(output: str) -> Dict:
    # Typical summary: rtt min/avg/max/mdev = 0.123/0.234/0.345/0.056 ms
    m = re.search(r"rtt .* = ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+) ms", output)
    if not m:
        return {"ok": False}
    return {
        "ok": True,
        "rtt_min_ms": float(m.group(1)),
        "rtt_avg_ms": float(m.group(2)),
        "rtt_max_ms": float(m.group(3)),
        "rtt_mdev_ms": float(m.group(4)),
    }


def parse_iperf(output: str, proto: str) -> Dict:
    """
    Parses iperf2 output (best-effort).
    For UDP we try to capture jitter and loss; for TCP we capture throughput.
    """
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    # Prefer last interval line containing "sec"
    candidate = None
    for ln in reversed(lines):
        if "sec" in ln and ("bits/sec" in ln):
            candidate = ln
            break

    if not candidate:
        return {"ok": False}

    parsed = {"ok": True, "line": candidate}

    # Throughput: "...  12.3 Mbits/sec" (or Kbits/sec, bits/sec)
    m = re.search(r"([0-9.]+)\s*([KMG]?)bits/sec", candidate)
    if m:
        val = float(m.group(1))
        unit = m.group(2)
        mult = {"": 1.0, "K": 1e3, "M": 1e6, "G": 1e9}.get(unit, 1.0)
        parsed["throughput_bps"] = val * mult

    if proto.lower() == "udp":
        # UDP line often contains: "jitter ms" and "lost/total (pct%)"
        mj = re.search(r"([0-9.]+)\s*ms", candidate)
        if mj:
            parsed["jitter_ms"] = float(mj.group(1))

        ml = re.search(r"(\d+)\s*/\s*(\d+)\s*\(([\d.]+)%\)", candidate)
        if ml:
            parsed["lost_packets"] = int(ml.group(1))
            parsed["total_packets"] = int(ml.group(2))
            parsed["loss_pct"] = float(ml.group(3))

    return parsed


def bps_to_iperf_rate(bps: int) -> str:
    """
    iperf2 "-b" accepts e.g. "64k", "5m". We'll use k/m where possible.
    """
    if bps >= 1_000_000 and bps % 1_000_000 == 0:
        return f"{bps // 1_000_000}m"
    if bps >= 1_000 and bps % 1_000 == 0:
        return f"{bps // 1_000}k"
    return str(bps)


def run_experiment(
    net: Mininet,
    flows: List[FlowSpec],
    base_port: int,
    ping_interval_s: float,
    ping_timeout_s: int,
    out_json: str
) -> None:
    """
    Runs flows according to schedule. Each flow:
      - starts iperf client
      - runs ping probes in parallel for the flow duration (RTT statistics)
    """
    info("* Running traffic experiment\n")
    t0 = time.time()

    procs = []  # (flow_spec, iperf_proc, ping_proc)
    results: List = []

    # Create quick lookup for hosts
    hosts: Dict[str, object] = {h.name: h for h in net.hosts}

    # Sort flows by start time to schedule them
    flows = sorted(flows, key=lambda f: f.start_s)

    for f in flows:
        now = time.time()
        target = t0 + f.start_s
        if target > now:
            time.sleep(target - now)

        src = hosts[f.src]
        dst = hosts[f.dst]
        dst_ip = dst.IP()
        dst_port = base_port + int(dst.name[1:])

        # Number of pings roughly covering duration
        ping_count = max(3, int(f.duration_s / ping_interval_s))

        # Ping in background (RTT measurements)
        ping_cmd = f"ping -c {ping_count} -i {ping_interval_s} -W {ping_timeout_s} {dst_ip}"

        # iperf client command
        if f.proto == "udp":
            rate = bps_to_iperf_rate(int(f.rate_bps))
            pkt = int(f.pkt_bytes)
            iperf_cmd = (
                f"iperf -c {dst_ip} -p {dst_port} -u "
                f"-b {rate} -t {f.duration_s} -l {pkt} -i 1 -S {f.tos_hex}"
            )
        else:
            # TCP
            if f.traffic_class == "interactive":
                # short-ish TCP transfer (bytes), approximates web/interactive bursts
                n_bytes = random.randint(200_000, 2_000_000)  # 0.2MB - 2MB
                iperf_cmd = (
                    f"iperf -c {dst_ip} -p {dst_port} "
                    f"-n {n_bytes} -i 1 -S {f.tos_hex}"
                )
            else:
                iperf_cmd = (
                    f"iperf -c {dst_ip} -p {dst_port} "
                    f"-t {f.duration_s} -i 1 -S {f.tos_hex}"
                )

        info(f"  -> Flow#{f.flow_id} {f.traffic_class} {f.src}->{f.dst} start={f.start_s}s dur={f.duration_s}s\n")

        iperf_p = src.pexec(iperf_cmd)
        ping_p = src.pexec(ping_cmd)

        procs.append((f, iperf_p, ping_p))

    # Collect outputs
    info("* Collecting results\n")
    for f, iperf_p, ping_p in procs:
        # iperf_out = iperf_p.communicate()[0]
        # ping_out = ping_p.communicate()[0]

        # popen(stdout=None) means output goes to terminal; better capture:
        # So we re-run with capture if needed:
        # if iperf_out is None:
        #     iperf_out = hosts[f.src].cmd(
        #         "echo 'WARNING: iperf output was not captured (set stdout capture if needed)'"
        #     )
        # if ping_out is None:
        #     ping_out = hosts[f.src].cmd(
        #         "echo 'WARNING: ping output was not captured (set stdout capture if needed)'"
        #     )

        # iperf_raw = iperf_out.decode() if isinstance(iperf_out, (bytes, bytearray)) else str(iperf_out)
        # ping_raw = ping_out.decode() if isinstance(ping_out, (bytes, bytearray)) else str(ping_out)

        # parsed = {
        #     "ping": parse_ping(ping_raw),
        #     "iperf": parse_iperf(iperf_raw, f.proto),
        # }


        parsed = {
            "ping": ping_p,
            "iperf": iperf_p,
        }

        # results.append(FlowResult(flow=f, iperf_raw=iperf_raw, ping_raw=ping_raw, parsed=parsed))
        results.append(parsed)

    # Save JSON
    payload = {
        "meta": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "scipy_ok": SCIPY_OK,
            "flows": len(flows),
        },
        "results": [
            {
                # "flow": asdict(r.flow),
                "parsed": r,
                # keep raw outputs if you want deep debugging:
                # "iperf_raw": r.iperf_raw,
                # "ping_raw": r.ping_raw,
            }
            for r in results
        ],
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    info(f"* Results saved to: {out_json}\n")


def main():
    parser = argparse.ArgumentParser(description="GEANT Mininet + Ryu traffic generator (SciPy schedule) + measurements")
    parser.add_argument("--controller-ip", default="127.0.0.1")
    parser.add_argument("--controller-port", type=int, default=6653)
    parser.add_argument("--flows", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--arrival-mean-s", type=float, default=2.0)
    parser.add_argument("--experiment-duration-s", type=int, default=120)

    parser.add_argument("--base-port", type=int, default=5000)
    parser.add_argument("--ping-interval-s", type=float, default=0.2)
    parser.add_argument("--ping-timeout-s", type=int, default=1)

    parser.add_argument("--core-delay", default=None, help='e.g., "5ms" to emulate WAN-like links')
    parser.add_argument("--core-bw", type=float, default=None, help="Mbps for switch-switch links")
    parser.add_argument("--host-delay", default=None, help='e.g., "1ms" for access links')
    parser.add_argument("--host-bw", type=float, default=None, help="Mbps for host-switch links")

    parser.add_argument("--out", default="geant_results.json")
    parser.add_argument("--cli", action="store_true", help="Drop into Mininet CLI after experiment")

    args = parser.parse_args()

    setLogLevel("info")

    topo = Geant(
        host_bw=args.host_bw,
        host_delay=args.host_delay,
        core_bw=args.core_bw,
        core_delay=args.core_delay,
        loss=0,
    )

    net = Mininet(
        topo=topo,
        controller=None,
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=True,
        build=True,
    )

    info(f"* Adding Ryu RemoteController {args.controller_ip}:{args.controller_port}\n")
    net.addController(
        "c0",
        controller=RemoteController,
        ip=args.controller_ip,
        port=args.controller_port,
    )

    info("* Starting network\n")
    net.start()

    # NOTE: pingAll will work only if your Ryu app installs forwarding rules (e.g., simple_switch_13)
    info("Waiting 30 sec for STP to coverge.")
    time.sleep(30)
    info("* Quick connectivity check (may fail if controller has no L2/L3 app)\n")
    _ = net.pingAll(timeout="1")

    # Prepare traffic
    host_names = [h.name for h in net.hosts]
    flows = generate_flow_schedule(
        host_names=host_names,
        n_flows=args.flows,
        seed=args.seed,
        arrival_mean_s=args.arrival_mean_s,
        experiment_duration_s=args.experiment_duration_s,
    )

    start_iperf_servers(net, base_port=args.base_port)

    # Run
    run_experiment(
        net=net,
        flows=flows,
        base_port=args.base_port,
        ping_interval_s=args.ping_interval_s,
        ping_timeout_s=args.ping_timeout_s,
        out_json=args.out,
    )

    if args.cli:
        from mininet.cli import CLI
        CLI(net)

    info("* Stopping network\n")
    net.stop()


if __name__ == "__main__":
    main()