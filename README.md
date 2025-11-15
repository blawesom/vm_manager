# VMAN - Virtual Machine Manager

A simple REST server to manage virtual machines with access to local storage and network.

## Features

- **VM Templates Management**: Create, list, and delete VM size templates
- **VM Lifecycle Management**: Create, start, stop, restart, and delete virtual machines
- **Disk Management**: Create, attach, detach, and delete disk images
- **Coherence Monitoring**: Automatic database coherence checks via OBSERVER service
- **Unified Logging**: Centralized logging system with rotation for all services

## Technology Stack

- **QEMU/QCOW2**: Virtualization (compute, network, and storage)
- **SQLite**: State management database
- **FastAPI**: REST API framework
- **Python 3.10+**: Programming language

## Architecture Support

**VMAN only supports x86_64 architecture.** The service requires `qemu-system-x86_64` or `qemu-kvm` and will reject other architectures. This limitation ensures compatibility and simplifies the implementation.

## Architecture

- **INTEL**: Main REST API service handling all API requests
- **VM_OPERATOR**: Local agent handling QEMU operations and filesystem
- **OBSERVER**: Local agent ensuring coherence between system and database (5s polling)
- **STATES DB**: SQLite database storing VM, template, and disk state

## Quick Start

### Prerequisites

- Python 3.10 or higher
- QEMU installed (`qemu-system-x86_64` or `qemu-kvm`) - **x86_64 architecture only**
- `qemu-img` tool available in PATH
- Host system must be x86_64 compatible

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd vm_manager
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. (Optional) Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your settings
```

4. Start the service:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### API Documentation

Once the service is running:
- **Interactive API docs**: http://localhost:8000/docs
- **OpenAPI spec**: http://localhost:8000/openapi.yaml
- **Health check**: http://localhost:8000/health

## Configuration

VMAN can be configured via environment variables. See `.env.example` for all available options.

### Key Configuration Options

- `VMAN_STORAGE_PATH`: Base directory for VM and disk storage (default: `/var/lib/vman`)
- `VMAN_DEFAULT_BOOT_DISK`: Path to default boot disk image (qcow2) to use for all VMs (optional)
- `VMAN_LOG_LEVEL`: Logging level - DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
- `VMAN_LOG_DIR`: Log directory (default: `./logs`)
- `VMAN_OPERATOR_DRY_RUN`: Enable dry-run mode for testing (default: 0)

See `.env.example` for complete configuration reference.

### Default Boot Disk

You can configure a default boot disk that will be automatically used for all new VMs. This is useful when you have a pre-built bootable image (e.g., created with `scripts/build_boot_disk.sh`).

**Setup:**
1. Build a boot disk using the provided scripts:
   ```bash
   sudo ./scripts/build_boot_disk.sh
   # Creates: storage/templates/alpine-minimal.qcow2
   ```

2. Set the environment variable:
   ```bash
   export VMAN_DEFAULT_BOOT_DISK=/path/to/storage/templates/alpine-minimal.qcow2
   ```

3. Start the service - all new VMs will automatically use this boot disk.

**Behavior:**
- When a VM is started without an existing `root.qcow2`, the default boot disk is copied to the VM's directory
- Each VM gets its own copy of the boot disk (independent filesystem)
- If `VMAN_DEFAULT_BOOT_DISK` is not set or the file doesn't exist, VMs will get an empty 10GB disk (default behavior)

## Usage Examples

### Create a VM Template

```bash
curl -X POST http://localhost:8000/templates \
  -H "Content-Type: application/json" \
  -d '{
    "name": "small",
    "cpu_count": 2,
    "ram_amount": 4
  }'
```

### Create a VM

```bash
curl -X POST http://localhost:8000/vms \
  -H "Content-Type: application/json" \
  -d '{
    "template_name": "small"
  }'
```

### Start a VM

```bash
curl -X POST http://localhost:8000/vms/{vm_id}/actions/start
```

### Create a Disk

```bash
curl -X POST http://localhost:8000/disks \
  -H "Content-Type: application/json" \
  -d '{
    "size": 20
  }'
```

### Attach Disk to VM

```bash
curl -X POST http://localhost:8000/disks/{disk_id}/attach \
  -H "Content-Type: application/json" \
  -d '{
    "vm_id": "your-vm-id"
  }'
```

## API Endpoints

### Templates
- `POST /templates` - Create template
- `GET /templates` - List templates
- `DELETE /templates/{name}` - Delete template

### VMs
- `POST /vms` - Create VM
- `GET /vms` - List VMs (optional `?state=running` filter)
- `GET /vms/{vm_id}` - Get VM details
- `DELETE /vms/{vm_id}` - Delete VM
- `POST /vms/{vm_id}/actions/start` - Start VM
- `POST /vms/{vm_id}/actions/stop` - Stop VM
- `POST /vms/{vm_id}/actions/restart` - Restart VM

### Disks
- `POST /disks` - Create disk
- `GET /disks` - List disks
- `GET /disks/{disk_id}` - Get disk details
- `DELETE /disks/{disk_id}` - Delete disk
- `POST /disks/{disk_id}/attach` - Attach disk to VM
- `POST /disks/{disk_id}/detach` - Detach disk from VM

### System
- `GET /health` - Health check (enhanced with system checks)
- `GET /observer/status` - OBSERVER service status
- `GET /openapi.yaml` - OpenAPI specification

## Testing

Run the test suite:

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html --cov-report=term tests/
```

Test coverage target: **80%**

## Development

### Project Structure

```
vm_manager/
├── app/
│   ├── main.py          # INTEL service (REST API)
│   ├── operator.py      # VM_OPERATOR service (QEMU operations)
│   ├── observer.py      # OBSERVER service (coherence checks)
│   ├── logging_config.py # Unified logging configuration
│   ├── models.py        # Database models
│   ├── schemas.py       # Pydantic schemas
│   └── db.py            # Database configuration
├── tests/               # Test suite
├── openapi/             # OpenAPI specification
├── docs/                # Documentation
└── requirements.txt     # Python dependencies
```

### Running in Development

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Logging

VMAN uses a unified logging system across all services:

- **Format**: `timestamp | level | service.module | message`
- **Services**: INTEL, OPERATOR, OBSERVER
- **Output**: Console (stdout) and file (default: `./logs/vman.log`)
- **Rotation**: Automatic (10MB default, 5 backups)

Logs are automatically rotated to prevent large files.

## Storage

VM and disk files are stored in the configured storage directory:

```
{VMAN_STORAGE_PATH}/
├── vms/
│   ├── {vm_id}/
│   │   ├── root.qcow2    # Root disk
│   │   ├── qemu.pid      # Process PID
│   │   ├── qmp.sock      # QMP socket
│   │   └── qemu.log      # QEMU logs
│   └── ...
└── disks/
    ├── {disk_id}.qcow2
    └── ...
```

## Troubleshooting

### QEMU not found
- Ensure `qemu-system-x86_64` or `qemu-kvm` is installed and in PATH
- Check with: `which qemu-system-x86_64`

### Permission errors
- Ensure storage directory is writable
- Check permissions: `ls -ld $VMAN_STORAGE_PATH`

### Database errors
- Check database file permissions: `ls -l states.db`
- Ensure SQLite is available

### Health check shows degraded status
- Check `/health` endpoint for specific issues
- Review logs in `./logs/vman.log`

## License

See [LICENSE](LICENSE) file for details.

## Contributing

1. Follow PEP8 coding conventions
2. Write unit tests for new features
3. Maintain 80% test coverage
4. Update documentation as needed

## Status

✅ All 6 development steps complete:
1. ✅ OpenAPI specification
2. ✅ INTEL service implementation
3. ✅ OPERATOR service (QEMU integration)
4. ✅ OBSERVER service (coherence monitoring)
5. ✅ Test suite (safety & security)
6. ✅ Unified logging system

**Current Status**: Production-ready core functionality

