#!/usr/bin/python
from mininet.node import OVSKernelSwitch
from mininet.topo import Topo
from mininet.link import TCLink

class Geant(Topo):

    def __init__(self):
        Topo.__init__(self)

        s = {}
        for i in range(1, 24):
            s[f's{i}'] = self.addSwitch(f's{i}', cls=OVSKernelSwitch)

        self.addLink(s['s1'], s['s7'], cls=TCLink)
        self.addLink(s['s2'], s['s4'], cls=TCLink)
        self.addLink(s['s2'], s['s7'], cls=TCLink)
        self.addLink(s['s2'], s['s18'], cls=TCLink)
        self.addLink(s['s2'], s['s23'], cls=TCLink)
        self.addLink(s['s2'], s['s11'], cls=TCLink)
        self.addLink(s['s2'], s['s6'], cls=TCLink)
        self.addLink(s['s3'], s['s21'], cls=TCLink)
        self.addLink(s['s4'], s['s14'], cls=TCLink)
        self.addLink(s['s4'], s['s20'], cls=TCLink)
        self.addLink(s['s5'], s['s8'], cls=TCLink)
        self.addLink(s['s5'], s['s16'], cls=TCLink)
        self.addLink(s['s5'], s['s11'], cls=TCLink)
        self.addLink(s['s6'], s['s19'], cls=TCLink)
        self.addLink(s['s6'], s['s13'], cls=TCLink)
        self.addLink(s['s6'], s['s18'], cls=TCLink)
        self.addLink(s['s7'], s['s21'], cls=TCLink)
        self.addLink(s['s7'], s['s18'], cls=TCLink)
        self.addLink(s['s8'], s['s9'], cls=TCLink)
        self.addLink(s['s8'], s['s20'], cls=TCLink)
        self.addLink(s['s10'], s['s16'], cls=TCLink)
        self.addLink(s['s11'], s['s20'], cls=TCLink)
        self.addLink(s['s11'], s['s21'], cls=TCLink)
        self.addLink(s['s11'], s['s22'], cls=TCLink)
        self.addLink(s['s11'], s['s16'], cls=TCLink)
        self.addLink(s['s12'], s['s22'], cls=TCLink)
        self.addLink(s['s15'], s['s20'], cls=TCLink)
        self.addLink(s['s17'], s['s23'], cls=TCLink)
        self.addLink(s['s18'], s['s21'], cls=TCLink)
        self.addLink(s['s22'], s['s23'], cls=TCLink)

topos = { 'geant': (lambda: Geant() ) }