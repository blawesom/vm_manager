# Default Boot Disk Feature

## Overview

The default boot disk feature allows you to configure a single bootable disk image that will be automatically used for all new VMs. This eliminates the need to manually create or copy boot disks for each VM.

## Configuration

Set the `VMAN_DEFAULT_BOOT_DISK` environment variable to the path of your boot disk image:

```bash
export VMAN_DEFAULT_BOOT_DISK=/var/lib/vman/templates/alpine-minimal.qcow2
```

Or in your `.env` file:
```
VMAN_DEFAULT_BOOT_DISK=/var/lib/vman/templates/alpine-minimal.qcow2
```

## How It Works

1. **When a VM is started** without an existing `root.qcow2`:
   - If `VMAN_DEFAULT_BOOT_DISK` is set and the file exists, it is **copied** to `{storage_path}/vms/{vm_id}/root.qcow2`
   - If `VMAN_DEFAULT_BOOT_DISK` is not set or doesn't exist, an empty 10GB disk is created (default behavior)

2. **Each VM gets its own copy**:
   - The default boot disk is copied (not linked) to each VM directory
   - This ensures each VM has an independent filesystem
   - Changes made in one VM do not affect others

3. **Explicit disk paths take precedence**:
   - If a `qcow2_path` is explicitly provided to `start_vm()`, it is used instead of the default

## Creating a Default Boot Disk

Use the provided scripts to create a minimal bootable disk:

```bash
# Build minimal Alpine Linux boot disk
sudo ./scripts/build_boot_disk.sh

# Output will be at: storage/templates/alpine-minimal.qcow2
```

Then configure it:
```bash
export VMAN_DEFAULT_BOOT_DISK=$(pwd)/storage/templates/alpine-minimal.qcow2
```

## Example Workflow

1. **Build the boot disk**:
   ```bash
   sudo ./scripts/build_boot_disk.sh
   ```

2. **Configure the service**:
   ```bash
   export VMAN_DEFAULT_BOOT_DISK=/var/lib/vman/templates/alpine-minimal.qcow2
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

3. **Create and start a VM**:
   ```bash
   # Create template
   curl -X POST http://localhost:8000/templates \
     -H "Content-Type: application/json" \
     -d '{"name": "small", "cpu_count": 2, "ram_amount": 4}'

   # Create VM
   curl -X POST http://localhost:8000/vms \
     -H "Content-Type: application/json" \
     -d '{"template_name": "small", "name": "my-vm"}'

   # Start VM - will automatically use default boot disk
   curl -X POST http://localhost:8000/vms/my-vm/actions/start
   ```

4. **The VM will boot** with the Alpine Linux system from the default boot disk.

## Disk Copy Behavior

- **Copy operation**: Uses `shutil.copy2()` which preserves metadata
- **Storage**: Each VM gets its own copy, so disk usage = `(default_boot_disk_size) * (number_of_vms)`
- **Performance**: Initial copy happens on first VM start (one-time cost)
- **Independence**: Each VM's disk is completely independent

## Troubleshooting

### Default boot disk not found

If the configured path doesn't exist, you'll see a warning in the logs:
```
WARNING: Default boot disk specified but not found: /path/to/disk.qcow2
```

The service will fall back to creating empty disks. Check:
- File path is correct
- File exists and is readable
- Permissions allow the service to read the file

### Disk copy fails

If copying the default boot disk fails:
- Check disk space (need space for each VM copy)
- Check permissions on source and destination directories
- Check logs for detailed error messages

### Using a different boot disk per VM

If you need different boot disks for different VMs:
1. Don't set `VMAN_DEFAULT_BOOT_DISK`
2. Manually copy the desired boot disk to `{storage_path}/vms/{vm_id}/root.qcow2` before starting the VM
3. The operator will use the existing `root.qcow2` if it's already present

## Implementation Details

- **Location**: `app/operator.py` - `LocalOperator.__init__()` and `start_vm()`
- **Environment variable**: `VMAN_DEFAULT_BOOT_DISK`
- **Fallback**: Creates empty 10GB disk if default not configured
- **Logging**: Logs when default boot disk is used (INFO level)

## Best Practices

1. **Use qcow2 format**: The default boot disk should be in qcow2 format for best compatibility
2. **Keep it minimal**: Smaller boot disks = faster copies and less storage usage
3. **Version control**: Consider versioning your boot disk templates
4. **Documentation**: Document what's installed in your default boot disk
5. **Testing**: Test the boot disk before setting it as default

