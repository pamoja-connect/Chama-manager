#!/bin/bash
set -e

echo "=== CONNECT post-merge setup ==="

# Install / sync Python dependencies
echo "Installing Python dependencies..."
pip install -q -r requirements.txt

echo "=== Post-merge setup complete ==="
