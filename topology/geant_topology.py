#!/usr/bin/python3
from mininet.node import OVSKernelSwitch
from mininet.topo import Topo
from mininet.link import TCLink


def _linkopts(bw=None, delay=None, loss=None):
    """Build TCLink options dict, skipping None values."""
    opts = {}
    if bw is not None:
        opts["bw"] = bw
    if delay is not None:
        opts["delay"] = delay
    if loss is not None:
        opts["loss"] = loss
    return opts


class Geant(Topo):
    """
    GEANT-like topology (23 switches) extended with one host per switch:
      - h1 connected to s1, ..., h23 connected to s23
      - host IPs are deterministic: 10.0.0.<id>/24

    Optional link shaping:
      - host_bw/host_delay for host-access links
      - core_bw/core_delay for switch-switch links
      - loss applies to both (simplify)
    """

    def __init__(self, host_bw=None, host_delay=None, core_bw=None, core_delay=None, loss=0):
        super().__init__()

        s = {}
        h = {}

        # Switches + hosts
        for i in range(1, 24):
            sname = f"s{i}"
            hname = f"h{i}"
            s[sname] = self.addSwitch(
                sname,
                cls=OVSKernelSwitch,
                protocols="OpenFlow13",  # important for Ryu apps that expect OF1.3
            )
            h[hname] = self.addHost(
                hname,
                ip=f"10.0.0.{i}/24",
            )

            # Host-access link
            self.addLink(
                h[hname], s[sname],
                cls=TCLink,
                **_linkopts(bw=host_bw, delay=host_delay, loss=loss)
            )

        # Core links (switch-switch)
        core = _linkopts(bw=core_bw, delay=core_delay, loss=loss)

        self.addLink(s["s1"], s["s7"], cls=TCLink, **core)
        self.addLink(s["s2"], s["s4"], cls=TCLink, **core)
        self.addLink(s["s2"], s["s7"], cls=TCLink, **core)
        self.addLink(s["s2"], s["s18"], cls=TCLink, **core)
        self.addLink(s["s2"], s["s23"], cls=TCLink, **core)
        self.addLink(s["s2"], s["s11"], cls=TCLink, **core)
        self.addLink(s["s2"], s["s6"], cls=TCLink, **core)
        self.addLink(s["s3"], s["s21"], cls=TCLink, **core)
        self.addLink(s["s4"], s["s14"], cls=TCLink, **core)
        self.addLink(s["s4"], s["s20"], cls=TCLink, **core)
        self.addLink(s["s5"], s["s8"], cls=TCLink, **core)
        self.addLink(s["s5"], s["s16"], cls=TCLink, **core)
        self.addLink(s["s5"], s["s11"], cls=TCLink, **core)
        self.addLink(s["s6"], s["s19"], cls=TCLink, **core)
        self.addLink(s["s6"], s["s13"], cls=TCLink, **core)
        self.addLink(s["s6"], s["s18"], cls=TCLink, **core)
        self.addLink(s["s7"], s["s21"], cls=TCLink, **core)
        self.addLink(s["s7"], s["s18"], cls=TCLink, **core)
        self.addLink(s["s8"], s["s9"], cls=TCLink, **core)
        self.addLink(s["s8"], s["s20"], cls=TCLink, **core)
        self.addLink(s["s10"], s["s16"], cls=TCLink, **core)
        self.addLink(s["s11"], s["s20"], cls=TCLink, **core)
        self.addLink(s["s11"], s["s21"], cls=TCLink, **core)
        self.addLink(s["s11"], s["s22"], cls=TCLink, **core)
        self.addLink(s["s11"], s["s16"], cls=TCLink, **core)
        self.addLink(s["s12"], s["s22"], cls=TCLink, **core)
        self.addLink(s["s15"], s["s20"], cls=TCLink, **core)
        self.addLink(s["s17"], s["s23"], cls=TCLink, **core)
        self.addLink(s["s18"], s["s21"], cls=TCLink, **core)
        self.addLink(s["s22"], s["s23"], cls=TCLink, **core)


topos = {"geant": (lambda: Geant())}