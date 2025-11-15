#!/bin/bash
# Build a minimal bootable reference disk for VMs
# Creates a small Alpine Linux-based qcow2 image that can be used as a template

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/../storage/templates"
OUTPUT_FILE="${OUTPUT_DIR}/alpine-minimal.qcow2"
DISK_SIZE="${DISK_SIZE:-2G}"  # Default 2GB, can be overridden
ALPINE_VERSION="${ALPINE_VERSION:-3.19}"
ALPINE_MIRROR="${ALPINE_MIRROR:-https://dl-cdn.alpinelinux.org/alpine}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check dependencies
check_dependencies() {
    local missing=()
    
    for cmd in qemu-img qemu-system-x86_64 mkfs.ext4 mount umount chroot; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        echo -e "${RED}Error: Missing required commands: ${missing[*]}${NC}" >&2
        echo "Please install: qemu-utils qemu-system-x86 linux-utils (or equivalent)" >&2
        exit 1
    fi
    
    # Check if running as root (needed for mount/chroot)
    if [ "$EUID" -ne 0 ]; then
        echo -e "${YELLOW}Warning: This script requires root privileges for mounting${NC}" >&2
        echo "Please run with sudo" >&2
        exit 1
    fi
}

# Cleanup function
cleanup() {
    local exit_code=$?
    
    # Unmount if mounted
    if [ -n "${MOUNT_POINT:-}" ] && mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
        echo -e "${YELLOW}Cleaning up mount point...${NC}"
        umount "$MOUNT_POINT" 2>/dev/null || true
    fi
    
    # Remove temporary directory
    if [ -n "${TEMP_DIR:-}" ] && [ -d "$TEMP_DIR" ]; then
        echo -e "${YELLOW}Cleaning up temporary directory...${NC}"
        rm -rf "$TEMP_DIR"
    fi
    
    # Remove loop device if attached
    if [ -n "${LOOP_DEV:-}" ] && [ -b "$LOOP_DEV" ]; then
        losetup -d "$LOOP_DEV" 2>/dev/null || true
    fi
    
    if [ $exit_code -ne 0 ]; then
        echo -e "${RED}Build failed with exit code $exit_code${NC}" >&2
    fi
    
    exit $exit_code
}

trap cleanup EXIT INT TERM

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Create temporary working directory
TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR"

echo -e "${GREEN}Building minimal bootable disk...${NC}"
echo "Output: $OUTPUT_FILE"
echo "Size: $DISK_SIZE"
echo ""

# Step 1: Create raw disk image
echo -e "${GREEN}[1/6] Creating raw disk image...${NC}"
qemu-img create -f raw disk.raw "$DISK_SIZE"

# Step 2: Partition the disk
echo -e "${GREEN}[2/6] Partitioning disk...${NC}"
parted -s disk.raw mklabel msdos
parted -s disk.raw mkpart primary ext4 1MiB 100%
parted -s disk.raw set 1 boot on

# Step 3: Setup loop device and format
echo -e "${GREEN}[3/6] Formatting partition...${NC}"
LOOP_DEV=$(losetup --find --show --partscan disk.raw)
PART_DEV="${LOOP_DEV}p1"

# Wait a moment for partition to be available
sleep 1

# Format as ext4
mkfs.ext4 -F -L "ALPINE_ROOT" "$PART_DEV"

# Step 4: Mount and install Alpine
echo -e "${GREEN}[4/6] Installing Alpine Linux...${NC}"
MOUNT_POINT="$TEMP_DIR/mount"
mkdir -p "$MOUNT_POINT"
mount "$PART_DEV" "$MOUNT_POINT"

# Download and extract Alpine
ALPINE_TARBALL="alpine-minirootfs-${ALPINE_VERSION}-x86_64.tar.gz"
if [ ! -f "$ALPINE_TARBALL" ]; then
    echo "Downloading Alpine Linux ${ALPINE_VERSION}..."
    wget -q "${ALPINE_MIRROR}/v${ALPINE_VERSION}/releases/x86_64/${ALPINE_TARBALL}" || {
        echo -e "${RED}Failed to download Alpine. Trying latest...${NC}"
        # Try to get latest version
        LATEST=$(curl -s "${ALPINE_MIRROR}/latest-stable/releases/x86_64/" | grep -oP 'alpine-minirootfs-\K[0-9.]+' | head -1)
        if [ -n "$LATEST" ]; then
            ALPINE_TARBALL="alpine-minirootfs-${LATEST}-x86_64.tar.gz"
            wget -q "${ALPINE_MIRROR}/latest-stable/releases/x86_64/${ALPINE_TARBALL}" || {
                echo -e "${RED}Failed to download Alpine Linux${NC}" >&2
                exit 1
            }
        else
            echo -e "${RED}Failed to determine Alpine version${NC}" >&2
            exit 1
        fi
    }
fi

echo "Extracting Alpine Linux..."
tar -xzf "$ALPINE_TARBALL" -C "$MOUNT_POINT"

# Step 5: Configure Alpine
echo -e "${GREEN}[5/6] Configuring system...${NC}"

# Setup basic filesystems
mount --bind /dev "$MOUNT_POINT/dev"
mount --bind /proc "$MOUNT_POINT/proc"
mount --bind /sys "$MOUNT_POINT/sys"

# Configure fstab
cat > "$MOUNT_POINT/etc/fstab" <<EOF
LABEL=ALPINE_ROOT / ext4 defaults,noatime 0 1
EOF

# Configure network (DHCP)
cat > "$MOUNT_POINT/etc/network/interfaces" <<EOF
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet dhcp
EOF

# Enable services
ln -sf /etc/init.d/networking "$MOUNT_POINT/etc/runlevels/default/networking"
ln -sf /etc/init.d/sshd "$MOUNT_POINT/etc/runlevels/default/sshd" 2>/dev/null || true

# Set root password (empty by default, can be changed)
chroot "$MOUNT_POINT" passwd -d root 2>/dev/null || true

# Install bootloader (Alpine uses extlinux, not GRUB)
echo -e "${GREEN}[6/6] Installing bootloader...${NC}"

# Install extlinux in chroot
chroot "$MOUNT_POINT" /bin/sh <<'EOF'
# Setup apk repositories
echo "https://dl-cdn.alpinelinux.org/alpine/v3.19/main" > /etc/apk/repositories
echo "https://dl-cdn.alpinelinux.org/alpine/v3.19/community" >> /etc/apk/repositories

# Update package index
apk update

# Install extlinux and required packages
apk add --no-cache syslinux linux-virt

# Install MBR bootloader
dd if=/usr/share/syslinux/mbr.bin of=/dev/loop0 bs=440 count=1

# Install extlinux to partition
extlinux --install /boot

# Generate extlinux config
cat > /boot/extlinux.conf <<EXTLINUX_EOF
DEFAULT alpine
LABEL alpine
  KERNEL /boot/vmlinuz-virt
  APPEND root=LABEL=ALPINE_ROOT quiet
  INITRD /boot/initramfs-virt
EXTLINUX_EOF
EOF

# Unmount chroot filesystems
umount "$MOUNT_POINT/dev"
umount "$MOUNT_POINT/proc"
umount "$MOUNT_POINT/sys"
umount "$MOUNT_POINT"

# Step 6: Convert to qcow2
echo -e "${GREEN}Converting to qcow2 format...${NC}"
qemu-img convert -f raw -O qcow2 -c disk.raw "$OUTPUT_FILE"

# Cleanup loop device
losetup -d "$LOOP_DEV"

# Get final size
FINAL_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)

echo ""
echo -e "${GREEN}✓ Boot disk created successfully!${NC}"
echo "  File: $OUTPUT_FILE"
echo "  Size: $FINAL_SIZE"
echo ""
echo "You can now use this as a reference disk:"
echo "  cp $OUTPUT_FILE /var/lib/vman/vms/{vm_id}/root.qcow2"

