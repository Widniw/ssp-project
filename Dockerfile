FROM python:3.8-alpine

RUN apk add --virtual .build-dependencies \
    gcc \
    git \
    libffi-dev \
    libgcc \
    libxslt-dev \
    libxml2-dev \
    make \
    musl-dev \
    openssl-dev \
    zlib-dev 

RUN apk add bash

ENV RYU_BRANCH=master
ENV RYU_TAG=v4.30
ENV HOME=/root
WORKDIR /root
RUN git clone -b ${RYU_BRANCH} https://github.com/osrg/ryu.git && \
    cd ryu && \
    git checkout tags/${RYU_TAG} && \
    pip install . && \
    pip install -r tools/optional-requires && \
    pip install --no-cache-dir "eventlet==0.30.2"

RUN apk del .build-dependencies

ENTRYPOINT ["/bin/ash"]