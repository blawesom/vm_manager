"""Basic smoke tests for the FastAPI app."""
import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app import db, models

client = TestClient(app)


def test_health_and_openapi():
    """Test health check and OpenAPI endpoints."""
    # Mock operator and observer to be healthy
    with patch('app.main._operator') as mock_op, \
         patch('app.main._observer') as mock_obs:
        mock_op.storage_path = "/tmp/test"
        mock_op.qemu_bin = "/usr/bin/qemu-system-x86_64"
        mock_op.qemu_img = "/usr/bin/qemu-img"
        mock_obs.running = True
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('os.access', return_value=True), \
             patch('app.db.SessionLocal') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value = mock_session
            mock_session.execute.return_value = None
            mock_session.close.return_value = None
            
            # Test health endpoint
            r = client.get("/health")
            assert r.status_code == 200
            
            # Test OpenAPI endpoint
            r2 = client.get("/openapi.yaml")
            assert r2.status_code in [200, 404]


@pytest.fixture(autouse=True)
def setup_db():
    """Setup and teardown database for each test."""
    models.Base.metadata.create_all(bind=db.engine)
    yield
    models.Base.metadata.drop_all(bind=db.engine)


def test_health_check_ok():
    """Test health check when all systems are ok."""
    # Mock operator and observer to be healthy
    with patch('app.main._operator') as mock_op, \
         patch('app.main._observer') as mock_obs:
        mock_op.storage_path = "/tmp/test"
        mock_op.qemu_bin = "/usr/bin/qemu-system-x86_64"
        mock_op.qemu_img = "/usr/bin/qemu-img"
        mock_obs.running = True
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('os.access', return_value=True), \
             patch('app.db.SessionLocal') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value = mock_session
            mock_session.execute.return_value = None
            mock_session.close.return_value = None
            
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "checks" in data


def test_health_check_degraded():
    """Test health check when systems are degraded."""
    with patch('app.main._operator') as mock_op, \
         patch('app.main._observer') as mock_obs:
        mock_op.storage_path = "/tmp/test"
        mock_op.qemu_bin = None  # QEMU not found
        mock_op.qemu_img = None
        mock_obs = None  # Observer not initialized
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('os.access', return_value=True), \
             patch('app.db.SessionLocal') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value = mock_session
            mock_session.execute.return_value = None
            mock_session.close.return_value = None
            
            response = client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"


def test_health_check_database_error():
    """Test health check with database error."""
    with patch('app.main._operator') as mock_op, \
         patch('app.main._observer') as mock_obs:
        mock_op.storage_path = "/tmp/test"
        mock_op.qemu_bin = "/usr/bin/qemu-system-x86_64"
        mock_op.qemu_img = "/usr/bin/qemu-img"
        mock_obs.running = True
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('os.access', return_value=True), \
             patch('app.db.SessionLocal') as mock_db:
            mock_db.side_effect = Exception("Database error")
            
            response = client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert "error" in data["checks"]["database"]


def test_health_check_storage_error():
    """Test health check with storage error."""
    with patch('app.main._operator') as mock_op, \
         patch('app.main._observer') as mock_obs:
        mock_op.storage_path = "/tmp/test"
        mock_op.qemu_bin = "/usr/bin/qemu-system-x86_64"
        mock_op.qemu_img = "/usr/bin/qemu-img"
        mock_obs.running = True
        
        with patch('pathlib.Path.exists', return_value=False), \
             patch('app.db.SessionLocal') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value = mock_session
            mock_session.execute.return_value = None
            mock_session.close.return_value = None
            
            response = client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"


def test_observer_status_running():
    """Test observer status endpoint when running."""
    with patch('app.main._observer') as mock_obs:
        mock_obs.running = True
        mock_obs.check_interval = 5.0
        mock_obs.last_issues = []
        
        response = client.get("/observer/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["check_interval"] == 5.0


def test_observer_status_stopped():
    """Test observer status endpoint when stopped."""
    with patch('app.main._observer') as mock_obs:
        mock_obs.running = False
        mock_obs.check_interval = 5.0
        mock_obs.last_issues = []
        
        response = client.get("/observer/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"


def test_observer_status_not_initialized():
    """Test observer status endpoint when not initialized."""
    with patch('app.main._observer', None):
        response = client.get("/observer/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_initialized"


def test_observer_status_with_issues():
    """Test observer status endpoint with issues."""
    from app.observer import CoherenceIssue
    
    with patch('app.main._observer') as mock_obs:
        mock_obs.running = True
        mock_obs.check_interval = 5.0
        mock_obs.last_issues = [
            CoherenceIssue("vm_state_mismatch", "vm-1", "VM running but DB says stopped")
        ]
        
        response = client.get("/observer/status")
        assert response.status_code == 200
        data = response.json()
        assert data["last_issues_count"] == 1
        assert len(data["last_issues"]) == 1
        assert data["last_issues"][0]["issue_type"] == "vm_state_mismatch"


def test_network_config():
    """Test network configuration endpoint."""
    with patch('app.main._network_manager') as mock_nm:
        from app.network_manager import NetworkConfig
        mock_config = NetworkConfig(
            vlan_id=100,
            bridge_name="br-vman",
            subnet="192.168.100.0/24",
            gateway="192.168.100.1",
            dns=["8.8.8.8", "8.8.4.4"]
        )
        mock_nm.get_network_config.return_value = mock_config
        mock_nm.get_allocated_ips.return_value = {"192.168.100.10"}
        mock_nm.subnet.hosts.return_value = [
            MagicMock() for _ in range(10)
        ]
        mock_nm.reserved_ips = {"192.168.100.0", "192.168.100.1", "192.168.100.255"}
        
        response = client.get("/network/config")
        assert response.status_code == 200
        data = response.json()
        assert data["vlan_id"] == 100
        assert data["bridge_name"] == "br-vman"
        assert "192.168.100.10" in data["allocated_ips"]


def test_network_config_not_configured():
    """Test network configuration endpoint when not configured."""
    with patch('app.main._network_manager', None):
        response = client.get("/network/config")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_configured"


def test_openapi_yaml():
    """Test OpenAPI YAML endpoint."""
    response = client.get("/openapi.yaml")
    # Should return 200 if file exists, 404 if not
    assert response.status_code in [200, 404]
    if response.status_code == 200:
        assert "openapi:" in response.text.lower() or "yaml" in response.headers.get("content-type", "").lower()
