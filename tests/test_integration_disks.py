"""Integration tests for disk operations.

Tests disk lifecycle: create, attach, detach, delete.
These tests validate disk operations with running VMs.
"""
import os
import pytest
import time
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.timeout(600)
class TestDiskOperations:
    """Test disk operations."""
    
    def test_create_disk(self, test_client: TestClient, cleanup_test_disks):
        """Test creating a disk."""
        response = test_client.post("/disks", json={"size": 5})
        assert response.status_code == 201
        disk_data = response.json()
        
        assert disk_data["size"] == 5
        assert disk_data["state"] == "available"
        assert disk_data["id"] is not None
        assert disk_data["mount_point"] is None
    
    def test_create_disk_with_mount_point(self, test_client: TestClient, cleanup_test_disks):
        """Test creating a disk with a mount point."""
        response = test_client.post("/disks", json={
            "size": 10,
            "mount_point": "/dev/xvdb"
        })
        assert response.status_code == 201
        disk_data = response.json()
        
        assert disk_data["size"] == 10
        assert disk_data["mount_point"] == "/dev/xvdb"
        assert disk_data["state"] == "available"
    
    def test_create_disk_invalid_size(self, test_client: TestClient):
        """Test creating a disk with invalid size should fail."""
        response = test_client.post("/disks", json={"size": 0})
        assert response.status_code == 422  # Validation error
    
    def test_list_disks(self, test_client: TestClient, cleanup_test_disks):
        """Test listing all disks."""
        # Create some disks
        for i in range(3):
            test_client.post("/disks", json={"size": 1})
        
        # List disks
        response = test_client.get("/disks")
        assert response.status_code == 200
        disks = response.json()
        assert len(disks) >= 3
        assert all(disk["state"] == "available" for disk in disks)
    
    def test_get_disk_details(self, test_client: TestClient, cleanup_test_disks):
        """Test getting disk details."""
        # Create disk
        response = test_client.post("/disks", json={"size": 5})
        disk_id = response.json()["id"]
        
        # Get disk details
        response = test_client.get(f"/disks/{disk_id}")
        assert response.status_code == 200
        disk_data = response.json()
        
        assert disk_data["id"] == disk_id
        assert disk_data["size"] == 5
        assert disk_data["state"] == "available"
    
    def test_get_nonexistent_disk(self, test_client: TestClient):
        """Test getting a non-existent disk should return 404."""
        response = test_client.get("/disks/nonexistent-disk-id")
        assert response.status_code == 404
    
    def test_delete_disk(self, test_client: TestClient, cleanup_test_disks):
        """Test deleting an available disk."""
        # Create disk
        response = test_client.post("/disks", json={"size": 1})
        disk_id = response.json()["id"]
        
        # Delete disk (should work in both dry-run and real mode)
        response = test_client.delete(f"/disks/{disk_id}")
        assert response.status_code == 204
        
        # Verify disk is gone from database
        response = test_client.get(f"/disks/{disk_id}")
        assert response.status_code == 404
    
    def test_delete_attached_disk_fails(self, test_client: TestClient, test_template: dict,
                                       cleanup_test_vms, cleanup_test_disks, qemu_available):
        """Test deleting an attached disk should fail."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create VM and disk
        vm_response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-disk-delete"
        })
        vm_id = vm_response.json()["id"]
        
        disk_response = test_client.post("/disks", json={"size": 1})
        disk_id = disk_response.json()["id"]
        
        # Start VM
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        
        # Attach disk
        test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
        
        # Try to delete attached disk
        response = test_client.delete(f"/disks/{disk_id}")
        assert response.status_code == 400
        assert "attached" in response.json()["detail"].lower()
        
        # Cleanup
        test_client.post(f"/disks/{disk_id}/detach")
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(2)
    
    def test_attach_disk_to_running_vm(self, test_client: TestClient, test_template: dict,
                                       cleanup_test_vms, cleanup_test_disks, qemu_available):
        """Test attaching a disk to a running VM."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create VM and disk
        vm_response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-disk-attach"
        })
        vm_id = vm_response.json()["id"]
        
        disk_response = test_client.post("/disks", json={"size": 1})
        disk_id = disk_response.json()["id"]
        
        # Start VM
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        
        # Attach disk
        response = test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
        assert response.status_code == 200
        
        # Verify disk is attached
        response = test_client.get(f"/disks/{disk_id}")
        assert response.status_code == 200
        disk_data = response.json()
        assert disk_data["state"] == "attached"
        assert disk_data["vm_id"] == vm_id
        assert disk_data["mount_point"] is not None
        
        # Cleanup
        test_client.post(f"/disks/{disk_id}/detach")
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(2)
    
    def test_attach_disk_missing_vm_id(self, test_client: TestClient, cleanup_test_disks):
        """Test attaching disk without VM ID should fail."""
        # Create disk
        response = test_client.post("/disks", json={"size": 1})
        disk_id = response.json()["id"]
        
        # Try to attach without vm_id
        response = test_client.post(f"/disks/{disk_id}/attach", json={})
        assert response.status_code == 400
        assert "vm_id" in response.json()["detail"].lower()
    
    def test_attach_disk_to_nonexistent_vm(self, test_client: TestClient, cleanup_test_disks):
        """Test attaching disk to non-existent VM should fail."""
        # Create disk
        response = test_client.post("/disks", json={"size": 1})
        disk_id = response.json()["id"]
        
        # Try to attach to non-existent VM
        response = test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": "nonexistent-vm"})
        assert response.status_code == 404
    
    def test_attach_disk_to_stopped_vm_fails(self, test_client: TestClient, test_template: dict,
                                             cleanup_test_vms, cleanup_test_disks):
        """Test attaching disk to stopped VM should fail."""
        # Create VM (not started) and disk
        vm_response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-stopped-attach"
        })
        vm_id = vm_response.json()["id"]
        
        disk_response = test_client.post("/disks", json={"size": 1})
        disk_id = disk_response.json()["id"]
        
        # Try to attach to stopped VM
        response = test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
        assert response.status_code == 400
        assert "running" in response.json()["detail"].lower()
    
    def test_detach_disk_from_running_vm(self, test_client: TestClient, test_template: dict,
                                         cleanup_test_vms, cleanup_test_disks, qemu_available):
        """Test detaching a disk from a running VM."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create VM and disk
        vm_response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-disk-detach"
        })
        vm_id = vm_response.json()["id"]
        
        disk_response = test_client.post("/disks", json={"size": 1})
        disk_id = disk_response.json()["id"]
        
        # Start VM and attach disk
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
        time.sleep(1)
        
        # Detach disk
        response = test_client.post(f"/disks/{disk_id}/detach")
        assert response.status_code == 200
        
        # Verify disk is available
        response = test_client.get(f"/disks/{disk_id}")
        assert response.status_code == 200
        disk_data = response.json()
        assert disk_data["state"] == "available"
        assert disk_data["vm_id"] is None
        assert disk_data["mount_point"] is None
        
        # Cleanup
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(2)
    
    def test_detach_disk_not_attached(self, test_client: TestClient, cleanup_test_disks):
        """Test detaching a disk that's not attached should fail."""
        # Create disk
        response = test_client.post("/disks", json={"size": 1})
        disk_id = response.json()["id"]
        
        # Try to detach
        response = test_client.post(f"/disks/{disk_id}/detach")
        assert response.status_code == 400
        assert "not attached" in response.json()["detail"].lower()
    
    def test_disk_hot_plug(self, test_client: TestClient, test_template: dict,
                          cleanup_test_vms, cleanup_test_disks, qemu_available):
        """Test disk hot-plugging: attach and detach while VM is running."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create VM and start it
        vm_response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-hotplug"
        })
        vm_id = vm_response.json()["id"]
        
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        
        # Verify VM is running
        response = test_client.get(f"/vms/{vm_id}")
        assert response.json()["state"] == "running"
        
        # Create disk
        disk_response = test_client.post("/disks", json={"size": 1})
        disk_id = disk_response.json()["id"]
        
        # Attach disk (hot-plug)
        response = test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
        assert response.status_code == 200
        time.sleep(1)
        
        # Verify disk attached
        response = test_client.get(f"/disks/{disk_id}")
        assert response.json()["state"] == "attached"
        
        # Verify VM still running
        response = test_client.get(f"/vms/{vm_id}")
        assert response.json()["state"] == "running"
        
        # Detach disk (hot-unplug)
        response = test_client.post(f"/disks/{disk_id}/detach")
        assert response.status_code == 200
        time.sleep(1)
        
        # Verify disk detached
        response = test_client.get(f"/disks/{disk_id}")
        assert response.json()["state"] == "available"
        
        # Verify VM still running
        response = test_client.get(f"/vms/{vm_id}")
        assert response.json()["state"] == "running"
        
        # Cleanup
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(2)
    
    def test_attach_already_attached_disk(self, test_client: TestClient, test_template: dict,
                                         cleanup_test_vms, cleanup_test_disks, qemu_available):
        """Test attaching an already attached disk should fail."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create VM and disk
        vm_response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-double-attach"
        })
        vm_id = vm_response.json()["id"]
        
        disk_response = test_client.post("/disks", json={"size": 1})
        disk_id = disk_response.json()["id"]
        
        # Start VM and attach disk
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
        time.sleep(1)
        
        # Try to attach again
        response = test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
        assert response.status_code == 400
        assert "already attached" in response.json()["detail"].lower()
        
        # Cleanup
        test_client.post(f"/disks/{disk_id}/detach")
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(2)
    
    def test_multiple_disks_attach_detach(self, test_client: TestClient, test_template: dict,
                                         cleanup_test_vms, cleanup_test_disks, qemu_available):
        """Test attaching and detaching multiple disks."""
        if not qemu_available or os.environ.get("VMAN_OPERATOR_DRY_RUN") == "1":
            pytest.skip("QEMU not available or dry-run mode enabled")
        
        # Create VM and start it
        vm_response = test_client.post("/vms", json={
            "template_name": test_template["name"],
            "name": "test-vm-multi-disk"
        })
        vm_id = vm_response.json()["id"]
        
        test_client.post(f"/vms/{vm_id}/actions/start")
        time.sleep(3)
        
        # Create multiple disks
        disk_ids = []
        for i in range(3):
            response = test_client.post("/disks", json={"size": 1})
            disk_ids.append(response.json()["id"])
        
        # Attach all disks
        for disk_id in disk_ids:
            response = test_client.post(f"/disks/{disk_id}/attach", json={"vm_id": vm_id})
            assert response.status_code == 200
            time.sleep(0.5)
        
        # Verify all attached
        for disk_id in disk_ids:
            response = test_client.get(f"/disks/{disk_id}")
            assert response.json()["state"] == "attached"
        
        # Detach all disks
        for disk_id in disk_ids:
            response = test_client.post(f"/disks/{disk_id}/detach")
            assert response.status_code == 200
            time.sleep(0.5)
        
        # Verify all available
        for disk_id in disk_ids:
            response = test_client.get(f"/disks/{disk_id}")
            assert response.json()["state"] == "available"
        
        # Cleanup
        test_client.post(f"/vms/{vm_id}/actions/stop")
        time.sleep(2)

