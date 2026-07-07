#!/bin/bash
set -euo pipefail

echo "Python version: $(python --version)"
echo "Installing CPU-only PyTorch..."
pip install --upgrade pip
pip install torch==2.4.1 torchvision==0.19.1 \
  --index-url https://download.pytorch.org/whl/cpu
echo "Installing application dependencies..."
pip install -r requirements.txt
