"""Unit tests for network manager module."""
import pytest
import subprocess
from unittest.mock import patch, MagicMock, Mock
from pathlib import Path
from app import network_manager


class TestNetworkManager:
    """Test NetworkManager class."""
    
    def test_init_defaults(self):
        """Test NetworkManager initialization with defaults."""
        nm = network_manager.NetworkManager()
        assert nm.vlan_id == 100
        assert nm.bridge_name == "br-vman"
        assert str(nm.subnet) == "192.168.100.0/24"
        assert nm.gateway == "192.168.100.1"
        assert nm.dns == ["8.8.8.8", "8.8.4.4"]
        assert len(nm.reserved_ips) == 3
        assert len(nm.allocated_ips) == 0
    
    def test_init_custom(self):
        """Test NetworkManager initialization with custom values."""
        nm = network_manager.NetworkManager(
            vlan_id=200,
            bridge_name="br-custom",
            subnet="10.0.0.0/24",
            gateway="10.0.0.1",
            dns=["1.1.1.1"]
        )
        assert nm.vlan_id == 200
        assert nm.bridge_name == "br-custom"
        assert str(nm.subnet) == "10.0.0.0/24"
        assert nm.gateway == "10.0.0.1"
        assert nm.dns == ["1.1.1.1"]
    
    def test_init_custom_gateway(self):
        """Test NetworkManager with custom gateway."""
        nm = network_manager.NetworkManager(
            subnet="192.168.1.0/24",
            gateway="192.168.1.10"
        )
        assert nm.gateway == "192.168.1.10"
    
    def test_init_dry_run(self):
        """Test NetworkManager with dry_run mode."""
        nm = network_manager.NetworkManager(dry_run=True)
        assert nm.dry_run is True
    
    @patch('app.network_manager.subprocess.run')
    def test_ensure_bridge_exists(self, mock_run):
        """Test ensure_bridge when bridge already exists."""
        mock_run.return_value = Mock(returncode=0)
        nm = network_manager.NetworkManager(dry_run=False)
        nm._interface_exists = Mock(return_value=True)
        nm.ensure_bridge()
        # Should not create bridge if it exists
        assert mock_run.call_count == 0
    
    @patch('app.network_manager.subprocess.run')
    def test_ensure_bridge_create(self, mock_run):
        """Test ensure_bridge creates bridge when it doesn't exist."""
        mock_run.return_value = Mock(returncode=0)
        nm = network_manager.NetworkManager(dry_run=False)
        nm._interface_exists = Mock(return_value=False)
        nm._has_ip = Mock(return_value=False)
        nm.ensure_bridge()
        # Should create bridge
        assert mock_run.call_count >= 2
    
    def test_ensure_bridge_dry_run(self):
        """Test ensure_bridge in dry-run mode."""
        nm = network_manager.NetworkManager(dry_run=True)
        with patch.object(nm, '_interface_exists', return_value=False):
            # Should not raise, just log
            nm.ensure_bridge()
    
    def test_allocate_ip(self):
        """Test IP allocation."""
        nm = network_manager.NetworkManager(subnet="192.168.100.0/24")
        ip = nm.allocate_ip("vm-1")
        assert ip not in nm.reserved_ips
        assert ip in nm.allocated_ips
        assert ip.startswith("192.168.100.")
    
    def test_allocate_ip_multiple(self):
        """Test multiple IP allocations."""
        nm = network_manager.NetworkManager(subnet="192.168.100.0/24")
        ip1 = nm.allocate_ip("vm-1")
        ip2 = nm.allocate_ip("vm-2")
        assert ip1 != ip2
        assert ip1 in nm.allocated_ips
        assert ip2 in nm.allocated_ips
    
    def test_allocate_ip_no_available(self):
        """Test IP allocation when no IPs available."""
        nm = network_manager.NetworkManager(subnet="192.168.100.0/30")  # Only 4 IPs, 3 reserved
        # Allocate the only available IP
        ip = nm.allocate_ip("vm-1")
        # Next allocation should fail
        with pytest.raises(RuntimeError, match="No available IPs"):
            nm.allocate_ip("vm-2")
    
    def test_release_ip(self):
        """Test IP release."""
        nm = network_manager.NetworkManager()
        ip = nm.allocate_ip("vm-1")
        assert ip in nm.allocated_ips
        nm.release_ip(ip)
        assert ip not in nm.allocated_ips
    
    def test_release_ip_not_allocated(self):
        """Test releasing IP that wasn't allocated."""
        nm = network_manager.NetworkManager()
        # Should not raise, just do nothing
        nm.release_ip("192.168.100.50")
    
    @patch('app.network_manager.subprocess.run')
    def test_create_tap_interface(self, mock_run):
        """Test TAP interface creation."""
        mock_run.return_value = Mock(returncode=0)
        nm = network_manager.NetworkManager(dry_run=False)
        nm._interface_exists = Mock(return_value=False)
        nm.ensure_bridge = Mock()
        
        tap_name = nm.create_tap_interface("vm-12345")
        assert tap_name.startswith("tap-")
        assert "12345" in tap_name or "vm-12" in tap_name
    
    def test_create_tap_interface_dry_run(self):
        """Test TAP interface creation in dry-run mode."""
        nm = network_manager.NetworkManager(dry_run=True)
        tap_name = nm.create_tap_interface("vm-1")
        assert tap_name.startswith("tap-")
    
    @patch('app.network_manager.subprocess.run')
    def test_create_tap_interface_exists(self, mock_run):
        """Test TAP interface creation when interface already exists."""
        nm = network_manager.NetworkManager(dry_run=False)
        nm._interface_exists = Mock(return_value=True)
        tap_name = nm.create_tap_interface("vm-1")
        # Should return name without creating
        assert tap_name.startswith("tap-")
    
    @patch('app.network_manager.subprocess.run')
    def test_delete_tap_interface(self, mock_run):
        """Test TAP interface deletion."""
        mock_run.return_value = Mock(returncode=0)
        nm = network_manager.NetworkManager(dry_run=False)
        nm._interface_exists = Mock(return_value=True)
        nm.delete_tap_interface("tap-vm1")
        # Should delete interface
        assert mock_run.call_count >= 1
    
    def test_delete_tap_interface_dry_run(self):
        """Test TAP interface deletion in dry-run mode."""
        nm = network_manager.NetworkManager(dry_run=True)
        nm.delete_tap_interface("tap-vm1")
        # Should not raise
    
    def test_delete_tap_interface_not_exists(self):
        """Test deleting TAP interface that doesn't exist."""
        nm = network_manager.NetworkManager(dry_run=False)
        nm._interface_exists = Mock(return_value=False)
        # Should not raise, just return
        nm.delete_tap_interface("tap-nonexistent")
    
    @patch('app.network_manager.subprocess.run')
    def test_delete_tap_interface_error(self, mock_run):
        """Test TAP interface deletion handles errors."""
        mock_run.side_effect = [
            Mock(returncode=0),  # nomaster
            RuntimeError("Delete failed")  # delete
        ]
        nm = network_manager.NetworkManager(dry_run=False)
        nm._interface_exists = Mock(return_value=True)
        # Should not raise, just log warning
        nm.delete_tap_interface("tap-vm1")
    
    def test_get_network_config(self):
        """Test getting network configuration."""
        nm = network_manager.NetworkManager(
            vlan_id=100,
            bridge_name="br-test",
            subnet="192.168.1.0/24",
            gateway="192.168.1.1",
            dns=["8.8.8.8"]
        )
        config = nm.get_network_config()
        assert config.vlan_id == 100
        assert config.bridge_name == "br-test"
        assert config.subnet == "192.168.1.0/24"
        assert config.gateway == "192.168.1.1"
        assert config.dns == ["8.8.8.8"]
    
    def test_get_allocated_ips(self):
        """Test getting allocated IPs."""
        nm = network_manager.NetworkManager()
        ip1 = nm.allocate_ip("vm-1")
        ip2 = nm.allocate_ip("vm-2")
        allocated = nm.get_allocated_ips()
        assert ip1 in allocated
        assert ip2 in allocated
        assert len(allocated) == 2
        # Should return a copy
        allocated.add("192.168.100.99")
        assert "192.168.100.99" not in nm.allocated_ips
    
    @patch('app.network_manager.subprocess.run')
    def test_run_command_success(self, mock_run):
        """Test _run_command with successful command."""
        mock_run.return_value = Mock(returncode=0, stdout="output", stderr="")
        nm = network_manager.NetworkManager()
        result = nm._run_command(["test", "command"])
        assert result.returncode == 0
    
    @patch('app.network_manager.subprocess.run')
    def test_run_command_failure(self, mock_run):
        """Test _run_command with failed command."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="error")
        nm = network_manager.NetworkManager()
        with pytest.raises(RuntimeError):
            nm._run_command(["test", "command"], check=True)
    
    @patch('app.network_manager.subprocess.run')
    def test_run_command_timeout(self, mock_run):
        """Test _run_command with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)
        nm = network_manager.NetworkManager()
        with pytest.raises(RuntimeError, match="timed out"):
            nm._run_command(["test", "command"])
    
    @patch('app.network_manager.subprocess.run')
    def test_interface_exists(self, mock_run):
        """Test _interface_exists."""
        mock_run.return_value = Mock(returncode=0)
        nm = network_manager.NetworkManager()
        assert nm._interface_exists("eth0") is True
    
    @patch('app.network_manager.subprocess.run')
    def test_interface_not_exists(self, mock_run):
        """Test _interface_exists when interface doesn't exist."""
        mock_run.side_effect = RuntimeError("not found")
        nm = network_manager.NetworkManager()
        assert nm._interface_exists("nonexistent") is False
    
    @patch('app.network_manager.subprocess.run')
    def test_has_ip(self, mock_run):
        """Test _has_ip."""
        mock_run.return_value = Mock(returncode=0, stdout="inet 192.168.1.1")
        nm = network_manager.NetworkManager()
        assert nm._has_ip("eth0", "192.168.1.1") is True
    
    @patch('app.network_manager.subprocess.run')
    def test_has_ip_not_found(self, mock_run):
        """Test _has_ip when IP not found."""
        mock_run.return_value = Mock(returncode=0, stdout="inet 192.168.1.2")
        nm = network_manager.NetworkManager()
        assert nm._has_ip("eth0", "192.168.1.1") is False

