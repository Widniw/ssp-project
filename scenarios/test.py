import argparse
import json
import random
import re
import time
from subprocess import PIPE, STDOUT, TimeoutExpired

from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info

from topology.ssp_topology import SSPTopo

PING_RTT_RE = re.compile(r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms")
PING_STAT_RE = re.compile(r"(\d+)\s+packets transmitted,\s+(\d+)\s+received.*?(\d+)%\s+packet loss")

DEFAULT_FAIL_MODE = "secure"
ENABLE_OVS_RSTP_STP = True
ENABLE_PRELEARN = True


def enable_ovs_loop_protection(net):
    """Force OF13 + fail-mode and (R)STP on all bridges to prevent loops."""
    for sw in net.switches:
        sw.cmd(f"ovs-vsctl set bridge {sw.name} protocols=OpenFlow13")
        sw.cmd(f"ovs-vsctl set-fail-mode {sw.name} {DEFAULT_FAIL_MODE}")
        if ENABLE_OVS_RSTP_STP:
            sw.cmd(
                "sh -lc "
                f"\"ovs-vsctl set bridge {sw.name} rstp_enable=true 2>/dev/null "
                f"|| ovs-vsctl set bridge {sw.name} stp_enable=true 2>/dev/null\""
            )


def profiles_from_csv(csv: str):
    """
    Numeric ToS:
    - EF DSCP 46 -> 184
    - AF41 DSCP 34 -> 136
    """
    out = []
    for p in [x.strip().lower() for x in csv.split(",") if x.strip()]:
        if p == "voip":
            out.append({"name": "voip", "proto": "udp", "bitrate": "128K", "length": 160, "tos": 184})
        elif p == "video":
            out.append({"name": "video", "proto": "udp", "bitrate": "8M", "length": 1200, "tos": 136})
        elif p == "bulk":
            out.append({"name": "bulk", "proto": "tcp", "tos": 0})
        else:
            raise ValueError(f"Unknown profile: {p}")
    return out


def random_pairs(hosts, n_pairs: int, seed: int):
    """Pick random distinct (src,dst) pairs. Reproducible via seed."""
    rng = random.Random(seed)
    names = [h.name for h in hosts]
    pairs = set()
    cap = min(n_pairs, len(names) * (len(names) - 1))
    while len(pairs) < cap:
        a = rng.choice(names)
        b = rng.choice(names)
        if a != b:
            pairs.add((a, b))
    by = {h.name: h for h in hosts}
    return [(by[a], by[b]) for (a, b) in list(pairs)[:n_pairs]]


def quick_ping_ok(src, dst_ip: str) -> bool:
    """Fast connectivity check to avoid long hangs when topology isn't ready."""
    out = src.cmd(f"ping -c 1 -W 1 {dst_ip}")
    return "1 received" in out or "0% packet loss" in out


def parse_ping_output(out: str) -> dict:
    """Parse ping summary; returns RTT stats if available, else tx/rx/loss."""
    m = PING_RTT_RE.search(out)
    if m:
        return {
            "ok": True,
            "min_ms": float(m.group(1)),
            "avg_ms": float(m.group(2)),
            "max_ms": float(m.group(3)),
            "mdev_ms": float(m.group(4)),
        }
    s = PING_STAT_RE.search(out)
    if s:
        return {
            "ok": False,
            "tx": int(s.group(1)),
            "rx": int(s.group(2)),
            "loss_pct": int(s.group(3)),
        }
    return {"ok": False}


def start_ping_monitor(src, dst_ip: str, duration_s: int):
    """
    Start ping that runs during load.
    -i 0.2 -> 5 pings per second
    -w D   -> stop after D seconds (deadline)
    """
    deadline = max(2, duration_s + 2)
    cmd = f"ping -i 0.2 -W 1 -w {deadline} {dst_ip}"
    return src.popen(cmd, stdout=PIPE, stderr=STDOUT, text=True)


def start_iperf_server(dst, port: int):
    """Start iperf3 server that exits after one client."""
    return dst.popen(f"iperf3 -s -1 -p {port}", stdout=PIPE, stderr=STDOUT, text=True)


def start_iperf_client(src, dst_ip: str, duration_s: int, port: int, prof: dict):
    """Start iperf3 client for given profile (JSON output)."""
    tos = prof["tos"]
    if prof["proto"] == "tcp":
        cmd = f"iperf3 -c {dst_ip} -p {port} -t {duration_s} -S {tos} -J"
    else:
        cmd = f"iperf3 -c {dst_ip} -p {port} -t {duration_s} -u -b {prof['bitrate']} -l {prof['length']} -S {tos} -J"
    return src.popen(cmd, stdout=PIPE, stderr=STDOUT, text=True)


def parse_iperf3_client_json(out: str, prof: dict) -> dict:
    """Return compact iperf3 metrics from client JSON."""
    try:
        j = json.loads(out)
    except Exception:
        return {"ok": False, "error": "bad_json"}

    end = j.get("end", {})
    if prof["proto"] == "tcp":
        sum_recv = end.get("sum_received", {})
        sum_sent = end.get("sum_sent", {})
        use = sum_recv if "bits_per_second" in sum_recv else sum_sent
        return {
            "ok": True,
            "proto": "tcp",
            "throughput_bps": use.get("bits_per_second"),
            "retransmits": sum_sent.get("retransmits"),
        }

    s = end.get("sum", {})
    return {
        "ok": True,
        "proto": "udp",
        "throughput_bps": s.get("bits_per_second"),
        "jitter_ms": s.get("jitter_ms"),
        "lost_percent": s.get("lost_percent"),
    }


def wait_communicate(proc, timeout_s: int):
    """Communicate with timeout; returns (ok, output_text)."""
    try:
        out, _ = proc.communicate(timeout=timeout_s)
        return True, (out or "")
    except TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            out, _ = proc.communicate(timeout=2)
        except Exception:
            out = ""
        return False, (out or "")


def run_parallel_bundle(src, dst, profs, duration_s: int, port_base: int):
    """
    Run ALL iperf3 profiles in parallel between src->dst AND run ping during load.
    Returns: (ping_during_stats, flows_metrics_list)
    """
    dst_ip = dst.IP()

    # Start iperf3 servers first
    servers = []
    for i, _ in enumerate(profs):
        servers.append(start_iperf_server(dst, port_base + i))
    time.sleep(0.4)  # give servers time to bind

    # Start ping monitor (during load)
    ping_proc = start_ping_monitor(src, dst_ip, duration_s)

    # Start all clients (parallel load)
    clients = []
    for i, prof in enumerate(profs):
        clients.append((prof, start_iperf_client(src, dst_ip, duration_s, port_base + i, prof)))

    # Wait for clients
    flows = []
    client_timeout = duration_s + 20
    for prof, cli in clients:
        ok, out = wait_communicate(cli, client_timeout)
        if not ok:
            flows.append({"profile": prof["name"], "metrics": {"ok": False, "error": "timeout"}})
        else:
            flows.append({"profile": prof["name"], "metrics": parse_iperf3_client_json(out, prof)})

    # Drain/stop ping
    ping_ok, ping_out = wait_communicate(ping_proc, duration_s + 5)
    ping_stats = parse_ping_output(ping_out) if ping_ok else {"ok": False}

    # Best-effort drain servers
    for srv in servers:
        wait_communicate(srv, 2)

    return ping_stats, flows


def main():
    parser = argparse.ArgumentParser(description="GEANT Mininet traffic generator (parallel flows + ping under load).")
    parser.add_argument("--controller-ip", default="172.16.0.2")
    parser.add_argument("--controller-port", type=int, default=6633)

    parser.add_argument("--pairs", type=int, default=10)
    parser.add_argument("--duration", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--profiles", default="voip,video,bulk")

    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--out", default="results.json")
    parser.add_argument("--log", default="info", choices=["debug", "info", "warning", "error"])
    args = parser.parse_args()

    setLogLevel(args.log)
    profs = profiles_from_csv(args.profiles)

    net = Mininet(
        topo=SSPTopo(),
        build=False,
        autoSetMacs=True,
        autoStaticArp=False,
        switch=OVSKernelSwitch,
        link=TCLink,
        controller=None,
    )
    net.addController(RemoteController("c0", ip=args.controller_ip, port=args.controller_port))

    info("*** Starting network\n")
    net.build()
    net.start()

    enable_ovs_loop_protection(net)

    if args.warmup > 0:
        info(f"*** Warmup sleep: {args.warmup}s\n")
        time.sleep(args.warmup)

    if ENABLE_PRELEARN:
        info("*** Prelearn: pingAll()\n")
        loss = net.pingAll()
        info(f"*** pingAll loss: {loss}%\n")

    pairs = random_pairs(net.hosts, args.pairs, args.seed)

    results = {
        "meta": {
            "controller": {"ip": args.controller_ip, "port": args.controller_port},
            "pairs": args.pairs,
            "duration_s": args.duration,
            "seed": args.seed,
            "profiles": [p["name"] for p in profs],
            "warmup_s": args.warmup,
        },
        "tests": [],
    }

    try:
        for i, (src, dst) in enumerate(pairs):
            info(f"\n*** Pair {i+1}/{len(pairs)}: {src.name} -> {dst.name}\n")

            # quick pre-check so we don't waste time if topology still unstable
            if not quick_ping_ok(src, dst.IP()):
                info("    ! quick ping failed -> skipping bundle\n")
                results["tests"].append({
                    "pair": {"src": src.name, "dst": dst.name},
                    "ping_during": {"ok": False},
                    "flows": [{"profile": p["name"], "metrics": {"ok": False, "error": "no_connectivity"}} for p in profs],
                })
                continue

            # Unique port block per pair (avoids collisions/timewait issues)
            port_base = 5201 + i * 50

            ping_during, flows = run_parallel_bundle(src, dst, profs, args.duration, port_base)

            results["tests"].append({
                "pair": {"src": src.name, "dst": dst.name},
                "ping_during": ping_during,
                "flows": flows,
            })

    finally:
        info("\n*** Stopping network\n")
        net.stop()
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        info(f"*** Results saved to: {args.out}\n")


if __name__ == "__main__":
    main()
