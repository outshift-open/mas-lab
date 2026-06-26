#!/usr/bin/env bash
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# Run ON insomnia (Debian) as root or via: ssh gromit@192.168.0.163 'sudo bash -s' < fix-nvidia-insomnia-remote.sh
set -euo pipefail

echo "=== 1. Diagnose ==="
uname -r
lspci | grep -i nvidia || true
dpkg -l | grep -i nvidia || true
dkms status || true
mokutil --sb-state || true
grep -rE "non-free|contrib" /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null || true

echo "=== 2. Purge broken Debian nvidia (if present) ==="
apt-get purge -y 'nvidia-*' 'libnvidia-*' 2>/dev/null || true
apt-get autoremove -y || true

echo "=== 3. NVIDIA CUDA repo + open driver ==="
cd /tmp
wget -q https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update
apt-get install -y build-essential dkms linux-headers-amd64 firmware-misc-nonfree
apt-get install -y nvidia-open nvidia-driver nvidia-smi

echo "=== 4. DKMS status ==="
dkms status

echo "=== 5. Load module + nvidia-smi ==="
modprobe nvidia || true
nvidia-smi

echo "=== Driver version ==="
dpkg -l | grep -E 'nvidia-driver|nvidia-open' | head -5
