# VM Console Capture Implementation

## Summary

Implemented VM console output capture with automatic file size limiting (50kB) and API access.

## Changes Made

### 1. Operator Service (`app/operator.py`)

**Added Methods:**
- `_limit_console_file(console_file, max_size=50*1024)`: Truncates console file to keep only last 50kB
- `_truncate_console_if_needed(vm_id)`: Wrapper to truncate console for a specific VM

**Modified `start_vm` method:**
- Added `console_file = vm_dir / "console.txt"` definition
- Added `-serial file:{console_file}` to QEMU command to redirect serial console output

### 2. API Endpoint (`app/main.py`)

**New Endpoint:**
- `GET /vms/{vm_id}/console` - Returns VM console output
  - Automatically truncates console file before reading
  - Returns empty content if console file doesn't exist
  - Handles errors gracefully

### 3. Schema Definition (`app/schemas.py`)

**New Schema:**
- `VMConsole`: Response model for console endpoint
  - `vm_id`: VM identifier
  - `console`: Console output content
  - `size`: Content size in bytes
  - `file_size`: Actual file size (optional)
  - `message`: Optional message (optional)

### 4. OpenAPI Specification (`openapi/intel.yaml`)

**Added:**
- `/vms/{vm_id}/console` endpoint definition
- `VMConsole` schema definition

## How It Works

1. **Console Capture**: When a VM starts, QEMU's `-serial file:` option redirects the serial console (COM1/ttyS0) to `{vm_dir}/console.txt`

2. **Size Limiting**: 
   - Console file grows as VM outputs data
   - When file exceeds 50kB, it's truncated to keep only the last 50kB
   - Truncation happens:
     - Before API read (ensures fast response)
     - Uses binary mode to handle any content safely

3. **API Access**:
   - `GET /vms/{vm_id}/console` returns the console content
   - Automatically truncates before reading
   - Returns structured JSON with console content and metadata

## File Structure

After implementation, VM directory contains:

```
{VMAN_STORAGE_PATH}/vms/{vm_id}/
├── root.qcow2      # Root disk
├── qemu.pid        # Process PID
├── qmp.sock        # QMP socket
├── qemu.log        # QEMU logs
├── console.txt     # Console output (max 50kB) ← NEW
├── ip.txt          # Assigned IP
└── tap.txt         # TAP interface name
```

## Usage Example

```bash
# Start a VM
curl -X POST http://localhost:8000/vms/{vm_id}/actions/start

# Read console output
curl http://localhost:8000/vms/{vm_id}/console

# Response:
{
  "vm_id": "my-vm",
  "console": "Kernel boot messages...\nSystem logs...\n",
  "size": 12345,
  "file_size": 12345
}
```

## Technical Details

### Console Capture
- Uses QEMU's `-serial file:path` option
- Captures serial console output (kernel messages, system logs)
- File is written by QEMU process directly

### Size Limiting Algorithm
1. Check if file exists and size > 50kB
2. If yes, seek to (file_size - 50kB) position
3. Read last 50kB
4. Write back to file (truncates file)

### Error Handling
- Console file may not exist (VM not started)
- File may be locked (QEMU writing) - handled with try/except
- Binary data in console - handled with `errors='replace'`

## Testing Recommendations

1. **Unit Tests**:
   - Test `_limit_console_file` with various file sizes
   - Test console file creation in VM directory
   - Test API endpoint with missing/empty console file

2. **Integration Tests**:
   - Start VM and verify console.txt is created
   - Write to console (via VM) and verify capture
   - Test API endpoint returns console content
   - Test truncation when file exceeds 50kB

3. **Edge Cases**:
   - Console file doesn't exist
   - Console file is empty
   - Console file contains binary data
   - Console file is exactly 50kB
   - Console file is much larger than 50kB

## Future Enhancements

- WebSocket streaming for real-time console
- Console filtering by log level
- Search within console output
- Download console as file
- Multiple serial ports support
- Console history (keep multiple rotated files)

