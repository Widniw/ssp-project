#!/usr/bin/python
from mininet.node import OVSKernelSwitch
from mininet.topo import Topo
from mininet.link import TCLink

class SSPTopo(Topo):

    def __init__(self):
        Topo.__init__(self)

        switches = {}
        hosts = {}

        for i in range(1,5):
            switches[f'R{i}'] = self.addSwitch(f'R{i}', cls=OVSKernelSwitch)

        hosts[f'H1'] = self.addHost(f'H1', ip = "10.0.0.1/24")
        hosts[f'H2'] = self.addHost(f'H2', ip = "10.0.0.2/24")
        hosts[f'H3'] = self.addHost(f'H3', ip = "10.0.0.3/24")
        hosts[f'H4'] = self.addHost(f'H4', ip = "10.0.0.4/24")


        self.addLink(switches['R1'], switches['R2'], cls=TCLink)
        self.addLink(switches['R1'], switches['R3'], cls=TCLink)
        self.addLink(switches['R1'], switches['R4'], cls=TCLink)
        self.addLink(switches['R2'], switches['R4'], cls=TCLink)
        self.addLink(switches['R3'], switches['R4'], cls=TCLink)


        self.addLink(hosts['H1'], switches['R1'], cls=TCLink)
        self.addLink(hosts['H3'], switches['R1'], cls=TCLink)
        self.addLink(hosts['H2'], switches['R4'], cls=TCLink)
        self.addLink(hosts['H4'], switches['R4'], cls=TCLink)

topos = { 'SSPTopo': (lambda: SSPTopo() ) }