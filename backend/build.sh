#!/bin/bash
pip install --upgrade pip
pip install torch==2.1.0+cpu torchvision==0.16.0+cpu \
  --extra-index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
