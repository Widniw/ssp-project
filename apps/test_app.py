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
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
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
from ryu.lib.packet import arp
from ryu.ofproto import ofproto_v1_3_parser


class SimpleSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch, self).__init__(*args, **kwargs)
        self.topology_api_app = self
        self.topology = nx.DiGraph()
    
    # Switch connects to the controller, controller is gathering topology info
    @set_ev_cls(event.EventSwitchEnter)
    def get_topology_data(self, ev):
        switch_list = get_switch(self.topology_api_app, None)
        switches = [(switch.dp.id, [port.port_no for port in switch.ports]) for switch in switch_list]
        for switch in switches:
            self.topology.add_node(switch[0])

        links_list = get_link(self.topology_api_app, None)
        for link in links_list:
            self.topology.add_edge(link.src.dpid, link.dst.dpid, weight = 1, out_port = link.src.port_no)
        
        # Print DiGraph for debbuging purposes
        # print("DiGraph as text:")
        # for node in self.topology.nodes(data=True):
        #     node_id, node_attr = node
        #     print(f"Node {node_id}: {node_attr}")
        #     for neighbor, edge_attr in self.topology[node_id].items():
        #         print(f"  -> {neighbor}: {edge_attr}")

    # Install table-miss flow entry for the new switch
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        
        self.add_flow(datapath, 0, match, actions)
        self.logger.info(f"Switch {datapath.id}: Zainstalowano Table-Miss Flow (domyślne wysyłanie do kontrolera)")

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    # Packet-in handler
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        arp_pkt = pkt.get_protocol(arp.arp)

        if arp_pkt:
            self.logger.info(f"Packet-in from switch {datapath.id}, port {in_port}, eth_type={eth.ethertype}")
            print(f"{eth = }")
            print(f"{pkt = }")
            self.topology.add_node(arp_pkt.src_ip, mac = arp_pkt.src_mac)
            self.topology.add_edge(arp_pkt.src_ip, datapath.id, weight = 1, out_port = in_port)
            self.topology.add_edge(datapath.id, arp_pkt.src_ip, weight = 1, out_port = in_port)

            # Print DiGraph for debbuging purposes
            print("DiGraph as text:")
            for node in self.topology.nodes(data=True):
                node_id, node_attr = node
                print(f"Node {node_id}: {node_attr}")
                for neighbor, edge_attr in self.topology[node_id].items():
                    print(f"  -> {neighbor}: {edge_attr}")
            
            return
        
        self.logger.info(f"Packet-in from switch {datapath.id}, port {in_port}, eth_type={eth.ethertype}")


        #Skoro robimy pingall, to na podstawie arp request wypełnijmy DIGraph o hosty i będzie komplet,
        #Na biezaco wypisuj caly DiGraph, zeby sprawdzic, czy sa zawarte wszystkie informacje.
        #Potem będzie trzeba zareagować na każdy inny pakiet niz arp, tzn. wyznaczyc sciezke wg. wag i wgrac na
        #wszystkie switche po drodze flow entry zeby to doszlo
        #Cel, routing "ospf" dla identycznych laczy, czyli hop-count