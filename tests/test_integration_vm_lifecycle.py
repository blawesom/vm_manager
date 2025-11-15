"""Integration tests for VM lifecycle operations.

Tests the complete VM lifecycle: create, start, stop, restart, delete.
These tests validate that VMs work correctly with real QEMU (when available).
"""
import os
import pytest
import time
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient

from app import operator


@pytest.mark.integration
@pytest.mark.timeout(600)
class TestVMLifecycle:
    """Test VM lifecycle operations."""
    
    def test_create_vm(self, test_client: TestClient, test_template: dict, cleanup_test_vms):
        """Test creating a VM from a template."""
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-create"
        })
        assert response.status_code == 201
        vm_data = response.json()
        
        assert vm_data["id"] == "test-vm-create"
        assert vm_data["state"] == "stopped"
        assert vm_data["vm_template"]["name"] == test_template["name"]
        assert vm_data["vm_template"]["cpu_count"] == test_template["cpu_count"]
        assert vm_data["vm_template"]["ram_amount"] == test_template["ram_amount"]
    
    def test_create_vm_with_custom_name(self, test_client: TestClient, test_template: dict, cleanup_test_vms):
        """Test creating a VM with a custom name."""
        custom_name = f"custom-vm-{int(time.time())}"
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": custom_name
        })
        assert response.status_code == 201
        assert response.json()["id"] == custom_name
    
    def test_create_vm_without_name(self, test_client: TestClient, test_template: dict, cleanup_test_vms):
        """Test creating a VM without specifying a name (UUID generated)."""
        response = test_client.post("/vms", json={
            "template_name": test_template["name"]
        })
        assert response.status_code == 201
        vm_data = response.json()
        assert vm_data["id"] is not None
        assert len(vm_data["id"]) > 0
    
    def test_start_vm_dry_run(self, test_client: TestClient, test_template: dict, cleanup_test_vms, test_operator):
        """Test starting a VM in dry-run mode."""
        # Create VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-start"
        })
        assert response.status_code == 201
        vm_id = response.json()["id"]
        
        # Start VM (should work in dry-run mode)
        response = test_client.post(f"/vms/{vm_id}/actions/start")
        assert response.status_code == 202
        
        # Verify state updated
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 200
        vm_data = response.json()
        # In dry-run, state might be "running" or "error" depending on implementation
        assert vm_data["state"] in ["running", "stopped", "error"]
    
    def test_start_vm_with_qemu(self, test_client: TestClient, test_template: dict, 
                                cleanup_test_vms, qemu_available, test_operator):
        """Test starting a VM with real QEMU."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-start-qemu"
        })
        assert response.status_code == 201
        vm_id = response.json()["id"]
        
        # Start VM
        response = test_client.post(f"/vms/{vm_id}/actions/start")
        assert response.status_code == 202
        
        # Wait for VM to start
        time.sleep(3)
        
        # Verify VM is running
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 200
        vm_data = response.json()
        assert vm_data["state"] == "running"
        
        # Verify QEMU process exists
        vm_dir = test_operator.storage_path / "vms" / vm_id
        pid_file = vm_dir / "qemu.pid"
        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            # Check if process exists
            try:
                os.kill(pid, 0)  # Signal 0 doesn't kill, just checks existence
                process_exists = True
            except (OSError, ProcessLookupError):
                process_exists = False
            assert process_exists, "QEMU process should be running"
        
        # Stop VM
        response = test_client.post(f"/vms/{vm_id}/actions/stop")
        assert response.status_code == 202
        
        # Wait for VM to stop
        time.sleep(2)
        
        # Verify VM is stopped
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 200
        vm_data = response.json()
        assert vm_data["state"] == "stopped"
    
    def test_stop_vm(self, test_client: TestClient, test_template: dict, cleanup_test_vms, qemu_available):
        """Test stopping a running VM."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create and start VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-stop"
        })
        vm_id = response.json()["id"]
        
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        
        # Stop VM
        response = test_client.post(f"/vms/{vm_id}/actions/stop")
        assert response.status_code == 202
        
        # Wait for stop
        time.sleep(2)
        
        # Verify stopped
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 200
        assert response.json()["state"] == "stopped"
    
    def test_stop_vm_not_running(self, test_client: TestClient, test_template: dict, cleanup_test_vms):
        """Test stopping a VM that's not running should fail."""
        # Create VM (not started)
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-stop-not-running"
        })
        vm_id = response.json()["id"]
        
        # Try to stop
        response = test_client.post(f"/vms/{vm_id}/actions/stop")
        assert response.status_code == 400
        assert "not running" in response.json()["detail"].lower()
    
    def test_restart_vm(self, test_client: TestClient, test_template: dict, cleanup_test_vms, qemu_available):
        """Test restarting a VM."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create and start VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-restart"
        })
        vm_id = response.json()["id"]
        
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        
        # Restart VM
        response = test_client.post(f"/vms/{vm_id}/actions/restart")
        assert response.status_code == 202
        
        # Wait for restart
        time.sleep(4)
        
        # Verify VM is running after restart
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 200
        vm_data = response.json()
        assert vm_data["state"] == "running"
        
        # Stop for cleanup
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(2)
    
    def test_delete_vm(self, test_client: TestClient, test_template: dict, cleanup_test_vms):
        """Test deleting a VM."""
        # Create VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-delete"
        })
        vm_id = response.json()["id"]
        
        # Delete VM
        response = test_client.delete(f"/vms/{vm_id}")
        assert response.status_code == 204
        
        # Verify VM is gone
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 404
    
    def test_delete_running_vm(self, test_client: TestClient, test_template: dict, cleanup_test_vms, qemu_available):
        """Test deleting a running VM (should stop it first)."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create and start VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-delete-running"
        })
        vm_id = response.json()["id"]
        
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        
        # Delete running VM
        response = test_client.delete(f"/vms/{vm_id}")
        assert response.status_code == 204
        
        # Wait a bit
        time.sleep(2)
        
        # Verify VM is gone
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 404
    
    def test_vm_state_transitions(self, test_client: TestClient, test_template: dict, cleanup_test_vms, qemu_available):
        """Test VM state transitions: stopped -> running -> stopped."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-states"
        })
        vm_id = response.json()["id"]
        
        # Initial state: stopped
        response = test_client.get(f"/vms/{vm_id}")
        assert response.json()["state"] == "stopped"
        
        # Start: stopped -> running
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        response = test_client.get(f"/vms/{vm_id}")
        assert response.json()["state"] == "running"
        
        # Stop: running -> stopped
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(2)
        response = test_client.get(f"/vms/{vm_id}")
        assert response.json()["state"] == "stopped"
    
    def test_list_vms_filtered_by_state(self, test_client: TestClient, test_template: dict, cleanup_test_vms):
        """Test listing VMs filtered by state."""
        # Create multiple VMs
        vm_ids = []
        for i in range(3):
            response = test_client.post("/vms", json={
                "template_name": test_template["name"],
                "name": f"test-vm-filter-{i}"
            })
            vm_ids.append(response.json()["id"])
        
        # List all VMs
        response = test_client.get("/vms")
        assert response.status_code == 200
        all_vms = response.json()
        assert len(all_vms) >= 3
        
        # Filter by stopped state
        response = test_client.get("/vms?state=stopped")
        assert response.status_code == 200
        stopped_vms = response.json()
        assert len(stopped_vms) >= 3
        assert all(vm["state"] == "stopped" for vm in stopped_vms)
        
        # Filter by running state (should be empty)
        response = test_client.get("/vms?state=running")
        assert response.status_code == 200
        running_vms = response.json()
        assert len(running_vms) == 0 or all(vm["state"] == "running" for vm in running_vms)
    
    def test_get_vm_details(self, test_client: TestClient, test_template: dict, cleanup_test_vms):
        """Test getting VM details."""
        # Create VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-details"
        })
        vm_id = response.json()["id"]
        
        # Get VM details
        response = test_client.get(f"/vms/{vm_id}")
        assert response.status_code == 200
        vm_data = response.json()
        
        assert vm_data["id"] == vm_id
        assert vm_data["state"] == "stopped"
        assert vm_data["vm_template"]["name"] == test_template["name"]
    
    def test_get_nonexistent_vm(self, test_client: TestClient):
        """Test getting a non-existent VM should return 404."""
        response = test_client.get("/vms/nonexistent-vm-id")
        assert response.status_code == 404
    
    def test_start_already_running_vm(self, test_client: TestClient, test_template: dict, cleanup_test_vms, qemu_available):
        """Test starting an already running VM should fail."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create and start VM
        response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-already-running"
        })
        vm_id = response.json()["id"]
        
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        
        # Try to start again
        response = test_client.post(f"/vms/{vm_id}/actions/start")
        assert response.status_code == 400
        assert "already running" in response.json()["detail"].lower()
        
        # Cleanup
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(2)

