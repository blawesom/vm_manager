"""Tests for metadata service (AWS EC2 metadata API)."""
import pytest
import base64
import http.client
from pathlib import Path
from app import db, models, metadata_service


@pytest.fixture
def metadata_service_instance(test_db, temp_storage):
    """Create metadata service instance for testing."""
    # Note: In real tests, we'd need to mock the HTTP server or use a test port
    # For now, we'll test the core logic without starting the server
    service = metadata_service.MetadataService(
        db_session_factory=test_db,
        storage_path=temp_storage,
        bind_ip="127.0.0.1",  # Use localhost for testing
        port=18000,  # Use non-privileged port
        bridge_name="test-br"
    )
    return service


def test_get_vm_by_ip(test_db, temp_storage, test_template):
    """Test finding VM by IP address."""
    # Create VM with IP
    vm = models.VM(
        id="test-vm-1",
        template_name=test_template.name,
        state="running",
        local_ip="192.168.100.10"
    )
    test_db.add(vm)
    test_db.commit()
    
    # Create handler (we'll test the method directly)
    class TestHandler(metadata_service.MetadataRequestHandler):
        def __init__(self):
            self.db_session_factory = test_db
            self.storage_path = temp_storage
    
    handler = TestHandler()
    found_vm = handler._get_vm_by_ip("192.168.100.10")
    assert found_vm is not None
    assert found_vm.id == "test-vm-1"
    
    # Test with non-existent IP
    found_vm = handler._get_vm_by_ip("192.168.100.99")
    assert found_vm is None


def test_get_vm_by_mac(test_db, temp_storage, test_template):
    """Test finding VM by MAC address."""
    # Create VM
    vm = models.VM(
        id="test-vm-1",
        template_name=test_template.name,
        state="running"
    )
    test_db.add(vm)
    test_db.commit()
    
    # Store MAC address
    vm_dir = temp_storage / "vms" / "test-vm-1"
    vm_dir.mkdir(parents=True)
    (vm_dir / "mac.txt").write_text("52:54:00:12:34:56")
    
    class TestHandler(metadata_service.MetadataRequestHandler):
        def __init__(self):
            self.db_session_factory = test_db
            self.storage_path = temp_storage
    
    handler = TestHandler()
    found_vm = handler._get_vm_by_mac("52:54:00:12:34:56")
    assert found_vm is not None
    assert found_vm.id == "test-vm-1"
    
    # Test with non-existent MAC
    found_vm = handler._get_vm_by_mac("52:54:00:99:99:99")
    assert found_vm is None


def test_get_metadata(test_db, temp_storage, test_template):
    """Test getting metadata from database."""
    # Create VM
    vm = models.VM(
        id="test-vm-1",
        template_name=test_template.name,
        state="running"
    )
    test_db.add(vm)
    test_db.commit()
    
    # Create metadata
    metadata = models.VMMetadata(
        vm_id="test-vm-1",
        hostname="test-hostname",
        user_data="#!/bin/bash\necho 'test'",
        ssh_keys="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB test@example.com"
    )
    test_db.add(metadata)
    test_db.commit()
    
    class TestHandler(metadata_service.MetadataRequestHandler):
        def __init__(self):
            self.db_session_factory = test_db
            self.storage_path = temp_storage
    
    handler = TestHandler()
    found_metadata = handler._get_metadata("test-vm-1")
    assert found_metadata is not None
    assert found_metadata.hostname == "test-hostname"
    assert found_metadata.user_data == "#!/bin/bash\necho 'test'"
    assert found_metadata.ssh_keys is not None


def test_handle_metadata_request_instance_id(test_db, temp_storage, test_template):
    """Test metadata request for instance-id."""
    # Create VM
    vm = models.VM(
        id="test-vm-1",
        template_name=test_template.name,
        state="running",
        local_ip="192.168.100.10"
    )
    test_db.add(vm)
    test_db.commit()
    
    class TestHandler(metadata_service.MetadataRequestHandler):
        def __init__(self):
            self.db_session_factory = test_db
            self.storage_path = temp_storage
    
    handler = TestHandler()
    result = handler._handle_metadata_request("meta-data/instance-id", vm)
    assert result == "test-vm-1"


def test_handle_metadata_request_local_ipv4(test_db, temp_storage, test_template):
    """Test metadata request for local-ipv4."""
    # Create VM
    vm = models.VM(
        id="test-vm-1",
        template_name=test_template.name,
        state="running",
        local_ip="192.168.100.10"
    )
    test_db.add(vm)
    test_db.commit()
    
    class TestHandler(metadata_service.MetadataRequestHandler):
        def __init__(self):
            self.db_session_factory = test_db
            self.storage_path = temp_storage
    
    handler = TestHandler()
    result = handler._handle_metadata_request("meta-data/local-ipv4", vm)
    assert result == "192.168.100.10"


def test_handle_metadata_request_hostname(test_db, temp_storage, test_template):
    """Test metadata request for hostname."""
    # Create VM
    vm = models.VM(
        id="test-vm-1",
        template_name=test_template.name,
        state="running"
    )
    test_db.add(vm)
    test_db.commit()
    
    # Create metadata with hostname
    metadata = models.VMMetadata(
        vm_id="test-vm-1",
        hostname="my-custom-hostname"
    )
    test_db.add(metadata)
    test_db.commit()
    
    class TestHandler(metadata_service.MetadataRequestHandler):
        def __init__(self):
            self.db_session_factory = test_db
            self.storage_path = temp_storage
    
    handler = TestHandler()
    result = handler._handle_metadata_request("meta-data/hostname", vm)
    assert result == "my-custom-hostname"
    
    # Test without metadata (should return VM ID)
    vm2 = models.VM(
        id="test-vm-2",
        template_name=test_template.name,
        state="running"
    )
    test_db.add(vm2)
    test_db.commit()
    
    result = handler._handle_metadata_request("meta-data/hostname", vm2)
    assert result == "test-vm-2"


def test_handle_metadata_request_user_data(test_db, temp_storage, test_template):
    """Test metadata request for user-data (base64 encoded)."""
    # Create VM
    vm = models.VM(
        id="test-vm-1",
        template_name=test_template.name,
        state="running"
    )
    test_db.add(vm)
    test_db.commit()
    
    # Create metadata with user-data
    user_data = "#!/bin/bash\necho 'Hello from cloud-init'"
    metadata = models.VMMetadata(
        vm_id="test-vm-1",
        user_data=user_data
    )
    test_db.add(metadata)
    test_db.commit()
    
    class TestHandler(metadata_service.MetadataRequestHandler):
        def __init__(self):
            self.db_session_factory = test_db
            self.storage_path = temp_storage
    
    handler = TestHandler()
    result = handler._handle_metadata_request("user-data", vm)
    # Should be base64 encoded
    decoded = base64.b64decode(result).decode('utf-8')
    assert decoded == user_data
    
    # Test without user-data
    vm2 = models.VM(
        id="test-vm-2",
        template_name=test_template.name,
        state="running"
    )
    test_db.add(vm2)
    test_db.commit()
    
    result = handler._handle_metadata_request("user-data", vm2)
    assert result == ""


def test_handle_metadata_request_ssh_keys(test_db, temp_storage, test_template):
    """Test metadata request for SSH keys."""
    # Create VM
    vm = models.VM(
        id="test-vm-1",
        template_name=test_template.name,
        state="running"
    )
    test_db.add(vm)
    test_db.commit()
    
    # Create metadata with SSH keys
    ssh_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB test@example.com"
    metadata = models.VMMetadata(
        vm_id="test-vm-1",
        ssh_keys=ssh_key
    )
    test_db.add(metadata)
    test_db.commit()
    
    class TestHandler(metadata_service.MetadataRequestHandler):
        def __init__(self):
            self.db_session_factory = test_db
            self.storage_path = temp_storage
    
    handler = TestHandler()
    # Test public-keys listing
    result = handler._handle_metadata_request("meta-data/public-keys/", vm)
    assert "0=default" in result
    
    # Test getting SSH key
    result = handler._handle_metadata_request("meta-data/public-keys/0/openssh-key", vm)
    assert result == ssh_key


def test_extract_mac_from_path():
    """Test extracting MAC address from path."""
    class TestHandler(metadata_service.MetadataRequestHandler):
        def __init__(self):
            pass
    
    handler = TestHandler()
    
    # Test with MAC in path
    path = "meta-data/network/interfaces/macs/52:54:00:12:34:56/local-ipv4"
    mac = handler._extract_mac_from_path(path)
    assert mac == "52:54:00:12:34:56"
    
    # Test without MAC
    path = "meta-data/instance-id"
    mac = handler._extract_mac_from_path(path)
    assert mac is None


def test_metadata_service_initialization(temp_storage, test_db):
    """Test metadata service initialization."""
    service = metadata_service.MetadataService(
        db_session_factory=test_db,
        storage_path=temp_storage,
        bind_ip="127.0.0.1",
        port=18000,
        bridge_name="test-br"
    )
    assert service.bind_ip == "127.0.0.1"
    assert service.port == 18000
    assert service.bridge_name == "test-br"
    assert not service.is_running()

