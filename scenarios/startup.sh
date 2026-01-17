#!/bin/bash

RESULTS_DIR="/ssp-project/results"
RESULTS_FILE="${RESULTS_DIR}/test_output"

mkdir -p "${RESULTS_DIR}"
rm "${RESULTS_FILE}"

sleep 2
service openvswitch-switch start
sleep 2

{
    mn --controller=remote,ip=172.16.0.2,port=6633 --topo single,3 <<'EOF'
nodes
net
dump
h1 ping -c 3 h3

exit
EOF
} >"$RESULTS_FILE" 2>&1

bash
