#!/bin/sh
# Все установки выполняются только во временном контейнере Ubuntu.
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends python3 graphviz > /work/install.log
python3 /work/native_apt.py /work
