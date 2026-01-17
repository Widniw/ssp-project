# Copyright (C) 2011 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
An OpenFlow 1.0 L2 learning switch implementation.
"""


from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.mac import haddr_to_bin
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link
import networkx as nx
import matplotlib.pyplot as plt


class SimpleSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch, self).__init__(*args, **kwargs)
        self.topology_api_app = self
        self.topology = nx.DiGraph()

    @set_ev_cls(event.EventSwitchEnter)
    def get_topology_data(self, ev):

        switch_list = get_switch(self.topology_api_app, None)
        switches = [(switch.dp.id, [port.port_no for port in switch.ports]) for switch in switch_list]
        for switch in switches:
            self.topology.add_node(switch[0])

        links_list = get_link(self.topology_api_app, None)
        links=[(link.src.dpid,link.dst.dpid,{'port':link.src.port_no}) for link in links_list]
        for link in links:
            self.topology.add_edge(link.src.dpid, link.dst.dpid, weight = 0, in_port = link.dst.port_no, out_port = link.src.port_no)

        self.draw_topology()

    def draw_topology(self):
        plt.figure(figsize=(6, 4))
        pos = nx.spring_layout(self.topology)
        nx.draw(self.topology, pos, with_labels=True, node_size=800, font_size=10)
        labels = nx.get_edge_attributes(self.topology, 'out_port')
        nx.draw_networkx_edge_labels(self.topology, pos, edge_labels=labels)
        plt.savefig('/apps/topology.png')
