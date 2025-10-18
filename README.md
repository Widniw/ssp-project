# How it works
Docker compose runs two containers:
- Ryu, IP 172.16.0.2
- Mininet, IP 172.16.0.3

# How to run it
Install docker
1. git clone https://github.com/Widniw/ssp-project/
2. docker build --rm -f Dockerfile -t ryu-alpine:latest .
3. docker compose up

# How to stop running containers
1. Ctrl+c
2. docker compose down
