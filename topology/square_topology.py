#!/usr/bin/python
from mininet.node import OVSKernelSwitch
from mininet.topo import Topo
from mininet.link import TCLink

class Square(Topo):

    def __init__(self):
        Topo.__init__(self)

        switches = {}
        hosts = {}

        for i in range(1,5):
            switches[f's{i}'] = self.addSwitch(f's{i}', cls=OVSKernelSwitch)

        hosts[f'h1_1'] = self.addHost(f'h1_1', ip = "10.0.0.11/24")
        hosts[f'h1_2'] = self.addHost(f'h1_2', ip = "10.0.0.12/24")
        hosts[f'h4_1'] = self.addHost(f'h4_1', ip = "10.0.0.41/24")
        hosts[f'h4_2'] = self.addHost(f'h4_2', ip = "10.0.0.42/24")


        self.addLink(switches['s1'], switches['s2'], cls=TCLink)
        self.addLink(switches['s2'], switches['s3'], cls=TCLink)
        self.addLink(switches['s3'], switches['s4'], cls=TCLink)
        self.addLink(switches['s4'], switches['s1'], cls=TCLink)

        self.addLink(hosts['h1_1'], switches['s1'], cls=TCLink)
        self.addLink(hosts['h1_2'], switches['s1'], cls=TCLink)
        self.addLink(hosts['h4_1'], switches['s4'], cls=TCLink)
        self.addLink(hosts['h4_2'], switches['s4'], cls=TCLink)

topos = { 'square': (lambda: Square() ) }