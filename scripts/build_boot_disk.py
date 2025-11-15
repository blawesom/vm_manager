#!/usr/bin/env python3
"""Build a minimal bootable reference disk for VMs.

This script creates a small Alpine Linux-based qcow2 image that can be used
as a template for VMs. The resulting disk is optimized for minimal size.

Usage:
    sudo python3 build_boot_disk.py [--size SIZE] [--output PATH]

Requirements:
    - Root privileges (for mounting)
    - qemu-img, qemu-system-x86_64
    - parted, mkfs.ext4, losetup
    - wget or curl
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def check_dependencies():
    """Check if all required commands are available."""
    required = ['qemu-img', 'qemu-system-x86_64', 'parted', 'mkfs.ext4', 'losetup', 'mount', 'umount']
    missing = []
    
    for cmd in required:
        if not shutil.which(cmd):
            missing.append(cmd)
    
    if missing:
        print(f"Error: Missing required commands: {', '.join(missing)}", file=sys.stderr)
        print("Please install: qemu-utils qemu-system-x86 parted e2fsprogs util-linux", file=sys.stderr)
        sys.exit(1)
    
    if os.geteuid() != 0:
        print("Error: This script requires root privileges for mounting", file=sys.stderr)
        print("Please run with sudo", file=sys.stderr)
        sys.exit(1)


def run_cmd(cmd, check=True, **kwargs):
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=check, **kwargs)
    return result


def download_alpine(version="3.19", mirror="https://dl-cdn.alpinelinux.org/alpine"):
    """Download Alpine Linux minirootfs tarball."""
    url = f"{mirror}/v{version}/releases/x86_64/alpine-minirootfs-{version}-x86_64.tar.gz"
    filename = f"alpine-minirootfs-{version}-x86_64.tar.gz"
    
    if os.path.exists(filename):
        print(f"Using existing {filename}")
        return filename
    
    print(f"Downloading Alpine Linux {version}...")
    if shutil.which("wget"):
        run_cmd(["wget", "-q", "--show-progress", url, "-O", filename])
    elif shutil.which("curl"):
        run_cmd(["curl", "-L", "-o", filename, url])
    else:
        print("Error: wget or curl required for downloading", file=sys.stderr)
        sys.exit(1)
    
    return filename


def build_boot_disk(output_path: Path, size: str = "2G", alpine_version: str = "3.19"):
    """Build a minimal bootable Alpine Linux disk."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        disk_raw = temp_path / "disk.raw"
        mount_point = temp_path / "mount"
        mount_point.mkdir()
        
        print(f"Creating {size} raw disk image...")
        run_cmd(["qemu-img", "create", "-f", "raw", str(disk_raw), size])
        
        print("Partitioning disk...")
        run_cmd(["parted", "-s", str(disk_raw), "mklabel", "msdos"])
        run_cmd(["parted", "-s", str(disk_raw), "mkpart", "primary", "ext4", "1MiB", "100%"])
        run_cmd(["parted", "-s", str(disk_raw), "set", "1", "boot", "on"])
        
        print("Setting up loop device...")
        result = run_cmd(["losetup", "--find", "--show", "--partscan", str(disk_raw)], 
                        capture_output=True, text=True)
        loop_dev = result.stdout.strip()
        part_dev = f"{loop_dev}p1"
        
        import time
        time.sleep(1)  # Wait for partition to be available
        
        try:
            print("Formatting partition...")
            run_cmd(["mkfs.ext4", "-F", "-L", "ALPINE_ROOT", part_dev])
            
            print("Mounting partition...")
            run_cmd(["mount", part_dev, str(mount_point)])
            
            try:
                print("Installing Alpine Linux...")
                alpine_tarball = download_alpine(alpine_version)
                
                print("Extracting Alpine Linux...")
                run_cmd(["tar", "-xzf", alpine_tarball, "-C", str(mount_point)])
                
                print("Configuring system...")
                # Setup fstab
                (mount_point / "etc" / "fstab").write_text("LABEL=ALPINE_ROOT / ext4 defaults,noatime 0 1\n")
                
                # Setup network
                (mount_point / "etc" / "network").mkdir(exist_ok=True)
                (mount_point / "etc" / "network" / "interfaces").write_text(
                    "auto lo\niface lo inet loopback\n\nauto eth0\niface eth0 inet dhcp\n"
                )
                
                # Mount chroot filesystems
                run_cmd(["mount", "--bind", "/dev", str(mount_point / "dev")])
                run_cmd(["mount", "--bind", "/proc", str(mount_point / "proc")])
                run_cmd(["mount", "--bind", "/sys", str(mount_point / "sys")])
                
                try:
                    print("Installing bootloader...")
                    # Install extlinux (Alpine uses extlinux, not GRUB)
                    chroot_cmd = [
                        "/bin/sh", "-c",
                        """
                        echo "https://dl-cdn.alpinelinux.org/alpine/v3.19/main" > /etc/apk/repositories
                        echo "https://dl-cdn.alpinelinux.org/alpine/v3.19/community" >> /etc/apk/repositories
                        apk update
                        apk add --no-cache syslinux linux-virt
                        dd if=/usr/share/syslinux/mbr.bin of=/dev/loop0 bs=440 count=1
                        extlinux --install /boot
                        cat > /boot/extlinux.conf <<'EOF'
DEFAULT alpine
LABEL alpine
  KERNEL /boot/vmlinuz-virt
  APPEND root=LABEL=ALPINE_ROOT quiet
  INITRD /boot/initramfs-virt
EOF
                        """
                    ]
                    run_cmd(["chroot", str(mount_point)] + chroot_cmd)
                finally:
                    # Unmount chroot filesystems
                    run_cmd(["umount", str(mount_point / "dev")])
                    run_cmd(["umount", str(mount_point / "proc")])
                    run_cmd(["umount", str(mount_point / "sys")])
                
            finally:
                print("Unmounting partition...")
                run_cmd(["umount", str(mount_point)])
        
        finally:
            print("Detaching loop device...")
            run_cmd(["losetup", "-d", loop_dev])
        
        print("Converting to qcow2...")
        run_cmd(["qemu-img", "convert", "-f", "raw", "-O", "qcow2", "-c", str(disk_raw), str(output_path)])
    
    # Get final size
    size_bytes = output_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    
    print(f"\n✓ Boot disk created successfully!")
    print(f"  File: {output_path}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"\nYou can use this as a reference disk:")
    print(f"  cp {output_path} /var/lib/vman/vms/{{vm_id}}/root.qcow2")


def main():
    parser = argparse.ArgumentParser(
        description="Build a minimal bootable reference disk for VMs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 build_boot_disk.py
  sudo python3 build_boot_disk.py --size 1G --output /var/lib/vman/templates/alpine.qcow2
        """
    )
    parser.add_argument(
        "--size",
        default="2G",
        help="Disk size (default: 2G)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent / "storage" / "templates" / "alpine-minimal.qcow2",
        help="Output qcow2 file path"
    )
    parser.add_argument(
        "--alpine-version",
        default="3.19",
        help="Alpine Linux version (default: 3.19)"
    )
    
    args = parser.parse_args()
    
    check_dependencies()
    build_boot_disk(args.output, args.size, args.alpine_version)


if __name__ == "__main__":
    main()

