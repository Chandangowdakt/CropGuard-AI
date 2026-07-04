#!/usr/bin/env bash
set -euo pipefail
# Render build: CPU PyTorch first (large wheel), then app dependencies.
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
