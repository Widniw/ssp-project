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
from ryu.lib.packet import arp, ipv4
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

    # Inject packet into the network
    def send_packet_out(self, datapath, port, pkt):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        pkt.serialize()
        data = pkt.data
        
        actions = [parser.OFPActionOutput(port)]
        
        out = parser.OFPPacketOut(datapath=datapath,
                                buffer_id=ofproto.OFP_NO_BUFFER,
                                in_port=ofproto.OFPP_CONTROLLER,
                                actions=actions,
                                data=data)
        datapath.send_msg(out)


    # Packet-in handler
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        arp_pkt = pkt.get_protocol(arp.arp)
        ipv4_pkt = pkt.get_protocol(ipv4.ipv4)


        #Ignore IPv6 Packet-ins
        ETHER_TYPE_IPV6 = 0x86DD
        if eth.ethertype == ETHER_TYPE_IPV6:
            return

        #Ignore LLDP Packet-ins
        ETHER_TYPE_LLDP = 0x88cc
        if eth.ethertype == ETHER_TYPE_LLDP:
            return
        
        self.logger.info(f"Packet-in from switch {datapath.id}, port {in_port}, eth_type={eth.ethertype}")
        print(f"{eth = }")
        print(f"{pkt = }")


        if arp_pkt:
            self.topology.add_node(arp_pkt.src_ip, mac = arp_pkt.src_mac)
            self.topology.add_edge(arp_pkt.src_ip, datapath.id, weight = 1, out_port = in_port)
            self.topology.add_edge(datapath.id, arp_pkt.src_ip, weight = 1, out_port = in_port)

            # Print DiGraph for debbuging purposes
            # print("DiGraph as text:")
            # for node in self.topology.nodes(data=True):
            #     node_id, node_attr = node
            #     print(f"Node {node_id}: {node_attr}")
            #     for neighbor, edge_attr in self.topology[node_id].items():
            #         print(f"  -> {neighbor}: {edge_attr}")

            ARP_REQUEST = 1
            ARP_REPLY = 2

            if arp_pkt.opcode == ARP_REQUEST and arp_pkt.dst_ip in self.topology:
                dst_mac = self.topology.nodes[arp_pkt.dst_ip]["mac"]

                pkt_reply = packet.Packet()
                
                pkt_reply.add_protocol(ethernet.ethernet(
                    ethertype=ether_types.ETH_TYPE_ARP,
                    dst=arp_pkt.src_mac,
                    src=dst_mac))
                
                pkt_reply.add_protocol(arp.arp(
                    opcode=ARP_REPLY,
                    src_mac=dst_mac,
                    src_ip=arp_pkt.dst_ip,
                    dst_mac=arp_pkt.src_mac,
                    dst_ip=arp_pkt.src_ip))
                
                self.send_packet_out(datapath, in_port, pkt_reply)
            
                return
            
        if ipv4_pkt:
            src_ip = ipv4_pkt.src
            dst_ip = ipv4_pkt.dst

            dijkstra_path = nx.dijkstra_path(self.topology, source = src_ip, target = dst_ip, weight = 'weight')
            intermediate_switches_on_djkstr_pth = dijkstra_path[1:-1]
            print(f"{dijkstra_path = }")
            print(f"{intermediate_switches_on_djkstr_pth = }")

            # Add flow on every switch on the path
            for switch in intermediate_switches_on_djkstr_pth:
                switch_index = dijkstra_path.index(switch)
                next_hop_index = switch_index + 1
                next_hop = dijkstra_path[next_hop_index]

                out_port = self.topology[switch][next_hop]['out_port']

                switch_obj_list = get_switch(self.topology_api_app, dpid=switch)
                datapath_obj = switch_obj_list[0].dp

                parser = datapath_obj.ofproto_parser

                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=src_ip,
                    ipv4_dst=dst_ip
                )
        
                actions = [parser.OFPActionOutput(out_port)]

                self.add_flow(datapath_obj, 1, match, actions)
            
            #After adding flows, let the first packet go along the path
            next_hop = dijkstra_path[dijkstra_path.index(datapath.id) + 1]
            first_hop_out_port = self.topology[datapath.id][next_hop]['out_port']
            self.send_packet_out(datapath, first_hop_out_port, pkt)
            

        #Skoro robimy pingall, to na podstawie arp request wypełnijmy DIGraph o hosty i będzie komplet,
        #Na biezaco wypisuj caly DiGraph, zeby sprawdzic, czy sa zawarte wszystkie informacje.
        #Potem będzie trzeba zareagować na każdy inny pakiet niz arp, tzn. wyznaczyc sciezke wg. wag i wgrac na
        #wszystkie switche po drodze flow entry zeby to doszlo
        #Cel, routing "ospf" dla identycznych laczy, czyli hop-count