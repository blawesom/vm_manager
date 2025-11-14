# VMAN Test Suite

This directory contains the comprehensive test suite for the VMAN (Virtual Machine Manager) system.

## Overview

The test suite includes:
- **Unit tests** for all API endpoints (templates, VMs, disks)
- **Unit tests** for OPERATOR service methods
- **Unit tests** for OBSERVER service coherence checks
- **Security tests** (SQL injection, path traversal, input validation)
- **Safety tests** (error handling, edge cases, invalid states)
- **State transition validation** tests

## Prerequisites

1. **Python 3.10+** installed
2. **Virtual environment** activated (recommended)
3. **Dependencies** installed:
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-cov httpx
   ```

## Running Tests

### Basic Test Execution

Run all tests:
```bash
pytest
```

Run with verbose output:
```bash
pytest -v
```

Run specific test file:
```bash
pytest tests/test_vms.py
```

Run specific test:
```bash
pytest tests/test_vms.py::test_create_vm_success
```

### Running with Coverage

Generate coverage report:
```bash
pytest --cov=app --cov-report=term tests/
```

Generate HTML coverage report:
```bash
pytest --cov=app --cov-report=html tests/
```

Generate both terminal and HTML reports:
```bash
pytest --cov=app --cov-report=term --cov-report=html tests/
```

View HTML coverage report:
```bash
# Open htmlcov/index.html in your browser
```

### Test Markers

The test suite uses markers to categorize tests:

- `@pytest.mark.unit` - Unit tests (fast, no external dependencies)
- `@pytest.mark.integration` - Integration tests (require QEMU)
- `@pytest.mark.slow` - Slow running tests
- `@pytest.mark.security` - Security-related tests
- `@pytest.mark.safety` - Safety and error handling tests

Run tests by marker:
```bash
# Run only unit tests
pytest -m unit

# Run only security tests
pytest -m security

# Skip integration tests
pytest -m "not integration"

# Run only fast tests (skip slow and integration)
pytest -m "not slow and not integration"
```

### Test Categories

#### API Endpoint Tests
- `test_templates.py` - Template management endpoints
- `test_vms.py` - VM lifecycle endpoints
- `test_disks.py` - Disk management endpoints
- `test_app.py` - System endpoints (health, OpenAPI)

#### Service Tests
- `test_operator.py` - OPERATOR service methods
- `test_observer.py` - OBSERVER service coherence checks

## Test Configuration

Test configuration is defined in `pytest.ini`:
- Test discovery patterns
- Output formatting
- Test markers
- Logging configuration

## Coverage Target

**Target Coverage: 80%**

Current coverage can be checked with:
```bash
pytest --cov=app --cov-report=term-missing tests/
```

The `--cov-report=term-missing` option shows which lines are not covered.

## Common Test Commands

```bash
# Run all tests with coverage
pytest --cov=app --cov-report=term --cov-report=html tests/

# Run tests in parallel (if pytest-xdist installed)
pytest -n auto

# Run tests with detailed output
pytest -v -s

# Run tests and stop on first failure
pytest -x

# Run tests and show local variables on failure
pytest -l

# Run tests with coverage and fail if below threshold
pytest --cov=app --cov-fail-under=80 tests/
```

## Test Structure

Each test file follows this structure:

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    """Setup and teardown database for each test."""
    # Create tables
    models.Base.metadata.create_all(bind=db.engine)
    yield
    # Cleanup
    models.Base.metadata.drop_all(bind=db.engine)

def test_example():
    """Test description."""
    response = client.post("/endpoint", json={"key": "value"})
    assert response.status_code == 201
    assert response.json()["key"] == "value"
```

## Troubleshooting

### Tests Fail with "ModuleNotFoundError: No module named 'httpx'"

Install missing dependencies:
```bash
pip install httpx
```

### Tests Fail with Database Errors

Ensure the database file is writable and the directory exists:
```bash
chmod 666 states.db  # If file exists
mkdir -p $(dirname states.db)  # If directory doesn't exist
```

### Tests Fail with "QEMU not found"

For tests that don't require QEMU, set dry-run mode:
```bash
export VMAN_OPERATOR_DRY_RUN=1
pytest
```

### Coverage Report Not Generated

Ensure pytest-cov is installed:
```bash
pip install pytest-cov
```

### Tests Run Slowly

Use markers to skip slow tests:
```bash
pytest -m "not slow"
```

Or run tests in parallel (requires pytest-xdist):
```bash
pip install pytest-xdist
pytest -n auto
```

## Test Data

Test data is managed through:
- **Fixtures** in `conftest.py` for shared test setup
- **Temporary storage** directories for disk and VM files
- **Database** setup/teardown for each test

## Writing New Tests

When adding new tests:

1. **Follow naming convention**: `test_<feature>_<scenario>()`
2. **Add docstrings**: Describe what the test validates
3. **Use appropriate markers**: Mark tests as unit, integration, security, etc.
4. **Test both success and failure cases**
5. **Test edge cases and boundary conditions**
6. **Test security aspects** (SQL injection, path traversal, etc.)

Example:
```python
@pytest.mark.unit
def test_create_vm_with_invalid_template():
    """Test creating VM with non-existent template fails."""
    response = client.post("/vms", json={"template_name": "nonexistent"})
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()
```

## Test Coverage by Module

Current coverage (as of last run):
- `app/models.py`: 100%
- `app/schemas.py`: 100%
- `app/db.py`: 100%
- `app/logging_config.py`: 86%
- `app/observer.py`: 77%
- `app/main.py`: 48%
- `app/network_manager.py`: 36%
- `app/operator.py`: 26%

**Overall Coverage: ~51%** (Target: 80%)

## Integration Tests

Integration tests require:
- QEMU installed and accessible
- KVM support (optional, can use TCG)
- Test storage directory with sufficient space
- Root or CAP_NET_ADMIN for network tests (optional)

Run integration tests:
```bash
pytest -m integration
```

Skip integration tests:
```bash
pytest -m "not integration"
```

## Continuous Integration

For CI/CD pipelines:

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-cov httpx

# Run tests with coverage
pytest --cov=app --cov-report=xml --cov-report=term tests/

# Fail if coverage below threshold
pytest --cov=app --cov-fail-under=80 tests/
```

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [FastAPI testing guide](https://fastapi.tiangolo.com/tutorial/testing/)

