"""Unit tests for VM template endpoints with safety and security verification."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import db, models

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Setup and teardown database for each test."""
    # Create tables
    models.Base.metadata.create_all(bind=db.engine)
    yield
    # Cleanup
    models.Base.metadata.drop_all(bind=db.engine)


def test_create_template_success():
    """Test successful template creation."""
    response = client.post("/templates", json={
        "name": "small",
        "cpu_count": 2,
        "ram_amount": 4
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "small"
    assert data["cpu_count"] == 2
    assert data["ram_amount"] == 4


def test_create_template_duplicate():
    """Test creating duplicate template fails."""
    client.post("/templates", json={"name": "small", "cpu_count": 2, "ram_amount": 4})
    response = client.post("/templates", json={"name": "small", "cpu_count": 4, "ram_amount": 8})
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_create_template_invalid_cpu():
    """Test template creation with invalid CPU count."""
    response = client.post("/templates", json={
        "name": "invalid",
        "cpu_count": 0,
        "ram_amount": 4
    })
    assert response.status_code == 422  # Validation error


def test_create_template_invalid_ram():
    """Test template creation with invalid RAM amount."""
    response = client.post("/templates", json={
        "name": "invalid",
        "cpu_count": 2,
        "ram_amount": -1
    })
    assert response.status_code == 422  # Validation error


def test_create_template_missing_fields():
    """Test template creation with missing required fields."""
    response = client.post("/templates", json={"name": "incomplete"})
    assert response.status_code == 422  # Validation error


def test_list_templates_empty():
    """Test listing templates when none exist."""
    response = client.get("/templates")
    assert response.status_code == 200
    assert response.json() == []


def test_list_templates_multiple():
    """Test listing multiple templates."""
    client.post("/templates", json={"name": "small", "cpu_count": 2, "ram_amount": 4})
    client.post("/templates", json={"name": "large", "cpu_count": 8, "ram_amount": 16})
    
    response = client.get("/templates")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = [t["name"] for t in data]
    assert "small" in names
    assert "large" in names


def test_delete_template_success():
    """Test successful template deletion."""
    client.post("/templates", json={"name": "temp", "cpu_count": 2, "ram_amount": 4})
    response = client.delete("/templates/temp")
    assert response.status_code == 204


def test_delete_template_not_found():
    """Test deleting non-existent template."""
    response = client.delete("/templates/nonexistent")
    assert response.status_code == 404


def test_delete_template_in_use():
    """Test deleting template that is in use by a VM."""
    # Create template and VM
    client.post("/templates", json={"name": "used", "cpu_count": 2, "ram_amount": 4})
    client.post("/vms", json={"template_name": "used"})
    
    # Try to delete template
    response = client.delete("/templates/used")
    assert response.status_code == 400
    assert "in use" in response.json()["detail"].lower()


def test_template_security_sql_injection():
    """Security test: SQL injection in template name."""
    # Try SQL injection in name field
    response = client.post("/templates", json={
        "name": "'; DROP TABLE vm_templates; --",
        "cpu_count": 2,
        "ram_amount": 4
    })
    # Should either create with sanitized name or reject
    # The important thing is it doesn't execute SQL
    assert response.status_code in [201, 400, 422]


def test_template_security_path_traversal():
    """Security test: Path traversal in template name."""
    response = client.post("/templates", json={
        "name": "../../etc/passwd",
        "cpu_count": 2,
        "ram_amount": 4
    })
    # Should handle safely (create with name as-is or reject)
    assert response.status_code in [201, 400, 422]


def test_template_security_very_large_values():
    """Security test: Very large integer values."""
    response = client.post("/templates", json={
        "name": "huge",
        "cpu_count": 999999999,
        "ram_amount": 999999999
    })
    # Should handle safely (create or reject, but not crash)
    assert response.status_code in [201, 400, 422]


def test_template_security_empty_name():
    """Security test: Empty string in name."""
    response = client.post("/templates", json={
        "name": "",
        "cpu_count": 2,
        "ram_amount": 4
    })
    # Should reject empty name
    assert response.status_code == 422


def test_template_security_special_characters():
    """Security test: Special characters in name."""
    response = client.post("/templates", json={
        "name": "test\n\r\t<script>alert('xss')</script>",
        "cpu_count": 2,
        "ram_amount": 4
    })
    # Should handle safely
    assert response.status_code in [201, 400, 422]

