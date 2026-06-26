#!/bin/bash
# Image2 MCP — Double-Click Setup for macOS
# Just double-click this file in Finder. Terminal will open and run the setup.
cd "$(dirname "$0")"
echo "Starting Image2 MCP Setup..."
bash scripts/setup.sh
echo ""
echo "Press any key to close this window..."
read -n 1
