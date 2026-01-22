import sys
import os
import time
import random
import json
import re
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from topology.geant_topology import Geant


def parse_iperf_throughput(filename):
    """
    Parses the iperf output file to extract the bandwidth.
    Looks for the summary line usually at the end of the file.
    """
    if not os.path.exists(filename):
        return "0.0 Mbit/s"

    last_throughput = "0.0 Mbit/s"
    
    # Regex to capture bandwidth (e.g., "9.62 Mbits/sec")
    # Matches: number + space + unit/sec
    regex = r"(\d+(?:\.\d+)?\s+[KMG]bits\/sec)"

    with open(filename, 'r') as f:
        content = f.read()
        matches = re.findall(regex, content)
        if matches:
            # Usually the last match is the average if running -t
            # We normalize 'sec' to 's' to match your requested format
            last_throughput = matches[-1].replace("sec", "s")
    
    return last_throughput

def wait_for_enter():
    print("\n" + "#"*40)
    input("  PRESS ENTER TO START THE SCENARIO  ")
    print("#"*40 + "\n")

def run_geant_scenario():
    # 1. Initialize Topology
    info('*** Loading Topology\n')
    topo = Geant(core_bw=10)

    # 2. Connect to Controller
    info('*** Connecting to Controller (172.16.0.2:6633)\n')
    c0 = RemoteController('c0', ip='172.16.0.2', port=6633)

    net = Mininet(topo=topo, 
                  controller=c0, 
                  switch=OVSKernelSwitch,
                  link=TCLink)

    net.start()

    # 3. Connectivity Check
    info('*** Running Pingall\n')
    net.pingAll()


    wait_for_enter()

    # 4. Wait 5 seconds before starting scenario
    info('*** Waiting 5 seconds...\n')
    time.sleep(5)

    # 5. Choose 10 unique pairs
    hosts = net.hosts
    if len(hosts) < 2:
        info('*** Error: Not enough hosts to create pairs.\n')
        net.stop()
        return

    # Generate all possible unique pairs
    all_pairs = []
    host_indices = list(range(len(hosts)))
    random.shuffle(host_indices)
    
    # We strictly need 10 pairs. 
    # Logic: Pick random source, pick random dest (not same), ensure uniqueness.
    # To keep it simple and robust:
    unique_pairs = []
    attempt_limit = 1000
    attempts = 0

    while len(unique_pairs) < 10 and attempts < attempt_limit:
        h1 = random.choice(hosts)
        h2 = random.choice(hosts)
        
        if h1 != h2:
            pair = (h1, h2)
            if pair not in unique_pairs and (h2, h1) not in unique_pairs:
                unique_pairs.append(pair)
        attempts += 1
    
    if len(unique_pairs) < 10:
        info(f'*** Warning: Only could generate {len(unique_pairs)} unique pairs.\n')

    # 6. Run Iperf Scenario
    info(f'*** Starting Iperf scenario with {len(unique_pairs)} pairs\n')
    
    # We run iperf for a long duration (-t 300) so they stay active
    # We will kill them manually when the scenario ends.
    output_files = {} # Store file paths to parse later
    
    for i, (src, dst) in enumerate(unique_pairs, start=1):
        info(f'*** Starting Pair {i}: {src.name} -> {dst.name}\n')
        
        # Start Server (in background)
        dst.cmd('iperf -s &')
        
        # Define output file for this pair
        outfile = f'iperf_pair_{i}.txt'
        output_files[i] = outfile
        
        # Start Client (in background, non-blocking)
        # -t 1000: Run long enough to ensure it's running when we stop
        src.cmd(f'iperf -c {dst.IP()} -t 1000 -i 1 > {outfile} &')
        
        # Wait a small fraction to simulate "adding" sequence, or proceed immediately
        # The prompt implies sequential addition.
        time.sleep(2)

    info('*** All 10 Iperfs are running.\n')

    # 7. Wait 5 seconds with all running
    info('*** Waiting 5 seconds with load active...\n')
    time.sleep(5)

    # 8. End Scenario and Cleanup
    info('*** Stopping Iperf processes\n')
    # Sending kill signals to hosts to stop iperf
    for h in hosts:
        h.cmd('killall -9 iperf')
    
    # 9. Save Results
    info('*** Parsing results\n')
    results = {}
    
    for i, outfile in output_files.items():
        throughput = parse_iperf_throughput(outfile)
        results[i] = throughput


    # Format JSON
    json_output = json.dumps(results, indent=4)
    info(f'*** Final Result:\n{json_output}\n')

    # Save to file
    with open('throughput_results.json', 'w') as f:
        f.write(json_output)

    info('*** Stopping Network\n')
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run_geant_scenario()