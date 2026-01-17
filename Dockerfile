FROM python:3.8-slim

# Install system dependencies needed for Ryu + matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    make \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    bash \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

ENV RYU_BRANCH=master
ENV RYU_TAG=v4.30
ENV HOME=/root

WORKDIR /root

# Clone and install Ryu and required Python packages
RUN git clone -b ${RYU_BRANCH} https://github.com/osrg/ryu.git && \
    cd ryu && \
    git checkout tags/${RYU_TAG} && \
    pip install . && \
    pip install -r tools/optional-requires && \
    pip install --no-cache-dir eventlet==0.30.2 && \
    pip install networkx && \
    pip install matplotlib

ENTRYPOINT ["python", "-m", "ryu.cmd.manager"]
