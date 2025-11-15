# Boot Disk Build Scripts

Scripts to build minimal bootable reference disks for VMs.

## Overview

These scripts create small, bootable qcow2 disk images that can be used as templates for VMs. The resulting disks are optimized for minimal size while still being fully functional.

## Scripts

### 1. `build_boot_disk.sh` (Recommended)

**Full-featured bash script** that builds a minimal Alpine Linux boot disk from scratch.

**Features:**
- Creates minimal Alpine Linux installation
- Installs GRUB bootloader
- Configures networking (DHCP)
- Optimized for smallest possible size (~50-100MB compressed)
- Fully automated

**Usage:**
```bash
# Build with defaults (2GB disk, Alpine 3.19)
sudo ./scripts/build_boot_disk.sh

# Custom size and version
sudo DISK_SIZE=1G ALPINE_VERSION=3.18 ./scripts/build_boot_disk.sh
```

**Output:**
- `storage/templates/alpine-minimal.qcow2`

**Requirements:**
- Root privileges (for mounting)
- `qemu-img`, `qemu-system-x86_64`
- `parted`, `mkfs.ext4`, `losetup`
- `wget` or `curl`
- Internet connection (to download Alpine)

---

### 2. `build_boot_disk.py`

**Python version** of the build script with the same functionality.

**Usage:**
```bash
# Build with defaults
sudo python3 scripts/build_boot_disk.py

# Custom options
sudo python3 scripts/build_boot_disk.py --size 1G --output /path/to/disk.qcow2
```

**Options:**
- `--size SIZE`: Disk size (default: 2G)
- `--output PATH`: Output file path
- `--alpine-version VERSION`: Alpine version (default: 3.19)

**Requirements:**
- Same as `build_boot_disk.sh`
- Python 3.6+

---

### 3. `build_boot_disk_simple.sh`

**Simplified script** that downloads pre-built cloud images (may be larger).

**Note:** This is a placeholder - for smallest size, use `build_boot_disk.sh`.

---

## Using the Boot Disk

Once built, you can use the disk as a reference for VMs:

### Option 1: Copy for each VM

```bash
# Copy to VM directory
cp storage/templates/alpine-minimal.qcow2 /var/lib/vman/vms/{vm_id}/root.qcow2
```

### Option 2: Use as template in operator

The operator will automatically use `root.qcow2` if it exists in the VM directory. You can:

1. Pre-create VMs with the template:
   ```bash
   mkdir -p /var/lib/vman/vms/{vm_id}
   cp storage/templates/alpine-minimal.qcow2 /var/lib/vman/vms/{vm_id}/root.qcow2
   ```

2. Or modify the operator to copy from template on first VM start.

---

## Disk Size Optimization

The scripts create disks optimized for minimal size:

- **Alpine Linux**: Smallest Linux distribution (~5MB base)
- **Minimal packages**: Only essential packages installed
- **Compressed qcow2**: Uses qcow2 compression
- **No swap**: No swap partition to save space
- **Minimal initramfs**: Only required drivers

**Typical sizes:**
- Raw disk: 2GB (sparse, mostly empty)
- Compressed qcow2: 50-100MB (depending on Alpine version)

---

## Customization

### Change Default Size

Edit the script or use environment variable:
```bash
export DISK_SIZE=1G
sudo ./scripts/build_boot_disk.sh
```

### Change Alpine Version

```bash
export ALPINE_VERSION=3.18
sudo ./scripts/build_boot_disk.sh
```

### Add Packages

After building, you can customize the disk:
```bash
# Mount the qcow2
sudo modprobe nbd max_part=8
sudo qemu-nbd --connect=/dev/nbd0 storage/templates/alpine-minimal.qcow2
sudo mount /dev/nbd0p1 /mnt

# Make changes
sudo chroot /mnt apk add <package>

# Unmount
sudo umount /mnt
sudo qemu-nbd --disconnect /dev/nbd0
```

---

## Troubleshooting

### "Missing required commands"

Install missing packages:
```bash
# Debian/Ubuntu
sudo apt-get install qemu-utils qemu-system-x86 parted e2fsprogs util-linux

# Fedora/RHEL
sudo dnf install qemu-img qemu-system-x86 parted e2fsprogs util-linux

# Alpine
sudo apk add qemu-img qemu-system-x86_64 parted e2fsprogs util-linux
```

### "Permission denied" or mount errors

The script requires root privileges:
```bash
sudo ./scripts/build_boot_disk.sh
```

### "Failed to download Alpine"

Check internet connection and Alpine mirror:
```bash
# Test mirror
curl -I https://dl-cdn.alpinelinux.org/alpine/v3.19/releases/x86_64/

# Use different mirror
export ALPINE_MIRROR=https://mirror.example.com/alpine
```

### Loop device errors

If loop device setup fails:
```bash
# Check available loop devices
ls -la /dev/loop*

# Increase loop device limit
sudo modprobe loop max_loop=16
```

---

## Integration with VMAN

### Automatic Template Usage

To automatically use the template when creating VMs, you could modify the operator:

```python
# In app/operator.py, start_vm method
if qcow2_path is None:
    qcow2_path = vm_dir / "root.qcow2"
    if not qcow2_path.exists():
        # Check for template
        template_path = self.storage_path / "templates" / "alpine-minimal.qcow2"
        if template_path.exists():
            # Copy template
            shutil.copy(template_path, qcow2_path)
        else:
            # Create empty disk (fallback)
            self.create_disk_image(qcow2_path, size_gb=10)
```

---

## Performance Tips

1. **Use KVM**: For faster VM startup
2. **Pre-allocate**: Use `qemu-img create -f qcow2 -o preallocation=metadata` for better performance
3. **Cache mode**: Use `cache=writeback` for better performance (less safe)
4. **Compression**: The qcow2 format already uses compression

---

## Security Notes

- The default root password is empty (disabled)
- SSH is not enabled by default
- Consider adding SSH keys or setting a root password after first boot
- The disk is minimal - add security packages as needed

---

## References

- [Alpine Linux](https://alpinelinux.org/)
- [QEMU Disk Images](https://www.qemu.org/docs/master/system/images.html)
- [GRUB Bootloader](https://www.gnu.org/software/grub/)

