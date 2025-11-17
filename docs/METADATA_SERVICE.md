# Cloud-init Metadata Service

## Overview

VMAN includes an AWS EC2-compatible metadata service that provides network-layer metadata to VMs for cloud-init initialization. This enables VMs to automatically configure themselves on first boot using cloud-init, including setting hostnames, running user-data scripts, and installing SSH keys.

## Architecture

The metadata service runs as a separate HTTP server on the bridge interface, listening on `169.254.169.254:80` (the standard link-local metadata service IP used by AWS EC2, OpenStack, and other cloud platforms). VMs on the bridge network can query this service to retrieve their configuration.

### Components

1. **Metadata Service** (`app/metadata_service.py`): HTTP server implementing AWS EC2 metadata API
2. **Database Schema** (`app/models.py`): `VMMetadata` table storing hostname, user-data, and SSH keys
3. **API Endpoints** (`app/main.py`): REST API for managing VM metadata
4. **Network Integration** (`app/network_manager.py`): Configures `169.254.169.254` on bridge interface
5. **Operator Integration** (`app/operator.py`): Stores VM MAC addresses for identification

## AWS EC2 Metadata API Compatibility

The metadata service implements the following AWS EC2 metadata API endpoints:

### Core Endpoints

- `GET /latest/meta-data/instance-id` - Returns the VM ID
- `GET /latest/meta-data/local-ipv4` - Returns the VM's local IP address
- `GET /latest/meta-data/public-ipv4` - Returns the VM's public IP (same as local for now)
- `GET /latest/meta-data/hostname` - Returns the VM hostname (or VM ID if not set)
- `GET /latest/meta-data/` - Lists available metadata paths

### Network Interface Endpoints

- `GET /latest/meta-data/network/interfaces/macs/{mac}/local-ipv4` - Returns IP address for a specific MAC address
- `GET /latest/meta-data/network/interfaces/macs/{mac}/` - Lists available network interface metadata

### User Data and SSH Keys

- `GET /latest/user-data` - Returns base64-encoded user-data script
- `GET /latest/meta-data/public-keys/` - Lists available SSH key indices
- `GET /latest/meta-data/public-keys/0/openssh-key` - Returns the first SSH public key

## Configuration

### Environment Variables

- `VMAN_METADATA_ENABLED` - Enable/disable metadata service (default: `1`)
- `VMAN_METADATA_BIND_IP` - IP address to bind metadata service (default: `169.254.169.254`)
- `VMAN_METADATA_PORT` - Port to listen on (default: `80`)

### Network Requirements

The metadata service requires:

1. **Bridge Interface**: The network bridge must be configured with the metadata service IP (`169.254.169.254`)
2. **Root Privileges**: Binding to `169.254.169.254:80` requires root privileges or `CAP_NET_BIND_SERVICE` capability
3. **VM Network Access**: VMs must be on the bridge network to access the metadata service

The network manager automatically configures `169.254.169.254` on the bridge interface when `ensure_bridge()` is called.

## Usage

### Setting VM Metadata

Use the REST API to configure metadata for a VM:

```bash
# Set hostname, user-data, and SSH keys
curl -X PUT http://localhost:8000/vms/my-vm/metadata \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "my-server",
    "user_data": "#!/bin/bash\necho \"Hello from cloud-init\"\napt-get update",
    "ssh_keys": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB... user@example.com"
  }'
```

### Getting VM Metadata

```bash
# Get current metadata
curl http://localhost:8000/vms/my-vm/metadata
```

### Clearing VM Metadata

```bash
# Remove all metadata
curl -X DELETE http://localhost:8000/vms/my-vm/metadata
```

## VM Identification

The metadata service identifies VMs using two methods:

1. **Source IP Address** (primary): The service uses the client's source IP to find the corresponding VM in the database
2. **MAC Address** (fallback): For network interface queries, the MAC address is extracted from the request path

VM MAC addresses are automatically stored in `{storage_path}/vms/{vm_id}/mac.txt` when VMs are started.

## User-Data Scripts

User-data scripts are cloud-init configuration scripts that run on first boot. They can be:

- **Shell scripts** (starting with `#!/bin/bash` or `#!/bin/sh`)
- **Cloud-init configuration** (YAML format)
- **Any text content** that cloud-init can process

The metadata service returns user-data as base64-encoded content, as required by the AWS EC2 metadata API.

### Example User-Data Script

```bash
#!/bin/bash
# Update system
apt-get update
apt-get upgrade -y

# Install packages
apt-get install -y nginx

# Configure service
systemctl enable nginx
systemctl start nginx

# Create a file
echo "Hello from cloud-init" > /tmp/cloud-init-test.txt
```

## SSH Keys

SSH public keys can be provided as a newline-separated list. Cloud-init will install these keys in the default user's `~/.ssh/authorized_keys` file.

### Example SSH Keys

```
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB... user1@example.com
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB... user2@example.com
```

## Complete Example Workflow

1. **Create a VM template**:
   ```bash
   curl -X POST http://localhost:8000/templates \
     -H "Content-Type: application/json" \
     -d '{"name": "small", "cpu_count": 2, "ram_amount": 4}'
   ```

2. **Create a VM**:
   ```bash
   curl -X POST http://localhost:8000/vms \
     -H "Content-Type: application/json" \
     -d '{"template_name": "small", "name": "web-server"}'
   ```

3. **Configure metadata**:
   ```bash
   curl -X PUT http://localhost:8000/vms/web-server/metadata \
     -H "Content-Type: application/json" \
     -d '{
       "hostname": "web-server",
       "user_data": "#!/bin/bash\necho \"Setting up web server\"\napt-get update\napt-get install -y nginx",
       "ssh_keys": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB... admin@example.com"
     }'
   ```

4. **Start the VM** (with cloud-init ready image):
   ```bash
   curl -X POST http://localhost:8000/vms/web-server/actions/start
   ```

5. **The VM will**:
   - Boot with the cloud-init ready image
   - Query the metadata service at `169.254.169.254`
   - Set the hostname to "web-server"
   - Run the user-data script (installing nginx)
   - Install the SSH key for admin@example.com

## Security Considerations

1. **Network Isolation**: The metadata service is only accessible from VMs on the bridge network. External access is not possible.

2. **VM Identification**: VMs are identified by their source IP address, which is assigned by the network manager. This prevents unauthorized access to other VMs' metadata.

3. **User-Data Validation**: User-data scripts are stored as-is. Consider validating or sanitizing user-data before storing if accepting input from untrusted sources.

4. **Root Privileges**: The metadata service requires root privileges to bind to `169.254.169.254:80`. Run the VMAN service with appropriate privileges or use `CAP_NET_BIND_SERVICE`.

## Troubleshooting

### Metadata Service Not Starting

**Error**: `Permission denied binding to 169.254.169.254:80`

**Solution**: Run VMAN with root privileges or grant `CAP_NET_BIND_SERVICE`:
```bash
sudo setcap cap_net_bind_service=+ep /path/to/python
```

### VM Cannot Reach Metadata Service

**Symptoms**: Cloud-init fails with "Connection refused" or "Network unreachable"

**Solutions**:
1. Verify the bridge interface has `169.254.169.254` configured:
   ```bash
   ip addr show br-vman | grep 169.254.169.254
   ```
2. Check that the VM is on the bridge network (not user-mode networking)
3. Verify the metadata service is running:
   ```bash
   curl http://169.254.169.254/latest/meta-data/instance-id
   ```

### Cloud-init Not Running

**Symptoms**: VM boots but cloud-init doesn't execute

**Solutions**:
1. Ensure the VM image has cloud-init installed
2. Check cloud-init logs in the VM: `/var/log/cloud-init.log`
3. Verify the metadata service is accessible from the VM
4. Check that user-data is properly formatted (starts with `#!/bin/bash` for shell scripts)

## Implementation Details

### Database Schema

The `VMMetadata` table stores:
- `vm_id` (primary key, foreign key to `vms.id`)
- `hostname` (optional)
- `user_data` (text, optional)
- `ssh_keys` (text, optional, newline-separated)
- `created_at` (timestamp)
- `updated_at` (timestamp)

### HTTP Server

The metadata service uses Python's `http.server` module to implement a simple HTTP server. It runs in a background thread and handles concurrent requests from multiple VMs.

### VM Lookup

The service uses a two-step lookup process:
1. First, try to find VM by source IP address (most common case)
2. If not found, extract MAC address from request path and look up by MAC

This ensures compatibility with both standard metadata queries and network interface-specific queries.

## References

- [AWS EC2 Instance Metadata](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-metadata.html)
- [Cloud-init Documentation](https://cloudinit.readthedocs.io/)
- [EC2 Metadata Service](https://github.com/aws/aws-sdk-go/blob/main/example/aws/ec2/metadata/main.go)

