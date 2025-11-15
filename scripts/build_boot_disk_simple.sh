#!/bin/bash
# Simple script to download and prepare a minimal Alpine Linux boot disk
# Uses pre-built Alpine cloud images (smallest option)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/../storage/templates"
OUTPUT_FILE="${OUTPUT_DIR}/alpine-minimal.qcow2"
ALPINE_VERSION="${ALPINE_VERSION:-3.19}"
ALPINE_MIRROR="${ALPINE_MIRROR:-https://dl-cdn.alpinelinux.org/alpine}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Building minimal bootable disk from Alpine cloud image...${NC}"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Download Alpine cloud image
CLOUD_IMAGE="alpine-standard-${ALPINE_VERSION}-x86_64.iso"
CLOUD_IMAGE_URL="${ALPINE_MIRROR}/v${ALPINE_VERSION}/releases/x86_64/${CLOUD_IMAGE}"

# Try to download cloud image
echo "Downloading Alpine Linux ${ALPINE_VERSION} cloud image..."
if ! wget -q --show-progress -O "${OUTPUT_DIR}/${CLOUD_IMAGE}" "$CLOUD_IMAGE_URL"; then
    echo -e "${YELLOW}Cloud image download failed, trying alternative method...${NC}"
    
    # Alternative: Create minimal qcow2 and use virt-customize if available
    if command -v virt-customize &> /dev/null; then
        echo "Using virt-customize to create minimal disk..."
        qemu-img create -f qcow2 "$OUTPUT_FILE" 1G
        # This would require more setup, so we'll use the manual method
    else
        echo -e "${RED}Please install virt-customize (libguestfs-tools) or use build_boot_disk.sh${NC}"
        exit 1
    fi
fi

# Convert ISO to qcow2 if we got an ISO
if [ -f "${OUTPUT_DIR}/${CLOUD_IMAGE}" ]; then
    echo "Converting ISO to qcow2..."
    # Extract and convert - this is simplified, actual process is more complex
    echo -e "${YELLOW}Note: ISO conversion requires manual steps or use build_boot_disk.sh for full automation${NC}"
fi

echo -e "${GREEN}For smallest disk, use: build_boot_disk.sh${NC}"
echo "This script downloads a pre-built image which may be larger."

