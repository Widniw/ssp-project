#!/bin/bash

service openvswitch-switch start

mn -c

python3 -m scenarios.test

