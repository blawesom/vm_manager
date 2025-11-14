from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from . import db, models, schemas, operator, observer
from sqlalchemy.orm import Session
from fastapi import status
import pathlib
import uuid
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

app = FastAPI(title="VMAN INTEL", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize operator and observer
_operator = operator.LocalOperator()
_observer: Optional[observer.LocalObserver] = None


def get_db():
    db_session = db.SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


@app.on_event("startup")
def startup_event():
    global _observer
    # create tables
    models.Base.metadata.create_all(bind=db.engine)
    
    # Initialize and start OBSERVER service
    _observer = observer.LocalObserver(
        db_session_factory=db.SessionLocal,
        operator=_operator,
        check_interval=5.0
    )
    _observer.start()
    logger.info("OBSERVER service started")


@app.on_event("shutdown")
def shutdown_event():
    global _observer
    # Stop OBSERVER service
    if _observer:
        _observer.stop()
        logger.info("OBSERVER service stopped")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/observer/status", tags=["observer"])
def observer_status():
    """Get OBSERVER service status and last detected issues."""
    global _observer
    if not _observer:
        return {"status": "not_initialized", "issues": []}
    
    return {
        "status": "running" if _observer.running else "stopped",
        "check_interval": _observer.check_interval,
        "last_issues_count": len(_observer.last_issues),
        "last_issues": [
            {
                "issue_type": issue.issue_type,
                "resource_id": issue.resource_id,
                "details": issue.details
            }
            for issue in _observer.last_issues
        ]
    }


@app.get("/openapi.yaml", tags=["meta"])
def openapi_yaml():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    spec_path = repo_root / "openapi" / "intel.yaml"
    if not spec_path.exists():
        raise HTTPException(status_code=404, detail="OpenAPI spec not found")
    return FileResponse(str(spec_path))


# Minimal template endpoints
@app.post("/templates", response_model=schemas.VMTemplate, status_code=status.HTTP_201_CREATED)
def create_template(payload: schemas.VMTemplateCreate, db: Session = Depends(get_db)):
    existing = db.query(models.VMTemplate).filter(models.VMTemplate.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Template already exists")
    tpl = models.VMTemplate(name=payload.name, cpu_count=payload.cpu_count, ram_amount=payload.ram_amount)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@app.get("/templates", response_model=list[schemas.VMTemplate])
def list_templates(db: Session = Depends(get_db)):
    items = db.query(models.VMTemplate).all()
    return items


@app.delete("/templates/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(name: str, db: Session = Depends(get_db)):
    tpl = db.query(models.VMTemplate).filter(models.VMTemplate.name == name).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    # Check if template is in use
    vms_using = db.query(models.VM).filter(models.VM.template_name == name).count()
    if vms_using > 0:
        raise HTTPException(status_code=400, detail=f"Template is in use by {vms_using} VM(s)")
    db.delete(tpl)
    db.commit()
    return None


# VM endpoints
@app.post("/vms", response_model=schemas.VM, status_code=status.HTTP_201_CREATED)
def create_vm(payload: schemas.VMCreate, db: Session = Depends(get_db)):
    # Check template exists
    template = db.query(models.VMTemplate).filter(models.VMTemplate.name == payload.template_name).first()
    if not template:
        raise HTTPException(status_code=400, detail="Template not found")
    
    # Generate VM ID
    vm_id = payload.name if payload.name else str(uuid.uuid4())
    
    # Check if VM ID already exists
    existing = db.query(models.VM).filter(models.VM.id == vm_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="VM with this ID already exists")
    
    # Create VM in database
    vm = models.VM(
        id=vm_id,
        template_name=payload.template_name,
        state="stopped"
    )
    db.add(vm)
    db.commit()
    db.refresh(vm)
    
    # Return with template relationship
    return {
        "id": vm.id,
        "vm_template": {
            "name": template.name,
            "cpu_count": template.cpu_count,
            "ram_amount": template.ram_amount
        },
        "state": vm.state,
        "local_ip": vm.local_ip
    }


@app.get("/vms", response_model=list[schemas.VM])
def list_vms(state: Optional[str] = Query(None, enum=["running", "stopped", "paused", "error"]), 
             db: Session = Depends(get_db)):
    query = db.query(models.VM)
    if state:
        query = query.filter(models.VM.state == state)
    
    vms = query.all()
    result = []
    for vm in vms:
        template = db.query(models.VMTemplate).filter(models.VMTemplate.name == vm.template_name).first()
        result.append({
            "id": vm.id,
            "vm_template": {
                "name": template.name,
                "cpu_count": template.cpu_count,
                "ram_amount": template.ram_amount
            },
            "state": vm.state,
            "local_ip": vm.local_ip
        })
    return result


@app.get("/vms/{vm_id}", response_model=schemas.VM)
def get_vm(vm_id: str, db: Session = Depends(get_db)):
    vm = db.query(models.VM).filter(models.VM.id == vm_id).first()
    if not vm:
        raise HTTPException(status_code=404, detail="VM not found")
    
    template = db.query(models.VMTemplate).filter(models.VMTemplate.name == vm.template_name).first()
    return {
        "id": vm.id,
        "vm_template": {
            "name": template.name,
            "cpu_count": template.cpu_count,
            "ram_amount": template.ram_amount
        },
        "state": vm.state,
        "local_ip": vm.local_ip
    }


@app.delete("/vms/{vm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vm(vm_id: str, db: Session = Depends(get_db)):
    vm = db.query(models.VM).filter(models.VM.id == vm_id).first()
    if not vm:
        raise HTTPException(status_code=404, detail="VM not found")
    
    # Stop VM if running
    if vm.state == "running":
        try:
            _operator.stop_vm(vm_id, force=True)
        except operator.OperatorError as e:
            logger.warning(f"Error stopping VM {vm_id} during delete: {e}")
    
    # Detach all disks
    disks = db.query(models.Disk).filter(models.Disk.vm_id == vm_id).all()
    for disk in disks:
        disk.vm_id = None
        disk.state = "available"
        disk.mount_point = None
    
    db.delete(vm)
    db.commit()
    return None


@app.post("/vms/{vm_id}/actions/start", status_code=status.HTTP_202_ACCEPTED)
def start_vm(vm_id: str, db: Session = Depends(get_db)):
    vm = db.query(models.VM).filter(models.VM.id == vm_id).first()
    if not vm:
        raise HTTPException(status_code=404, detail="VM not found")
    
    if vm.state == "running":
        raise HTTPException(status_code=400, detail="VM is already running")
    
    template = db.query(models.VMTemplate).filter(models.VMTemplate.name == vm.template_name).first()
    
    # Get disk path if VM has a root disk
    storage_path = Path(_operator.storage_path)
    vm_dir = storage_path / "vms" / vm_id
    qcow2_path = vm_dir / "root.qcow2" if (vm_dir / "root.qcow2").exists() else None
    
    try:
        _operator.start_vm(
            vm_id=vm_id,
            qcow2_path=qcow2_path,
            cpu_count=template.cpu_count,
            ram_gb=template.ram_amount
        )
        vm.state = "running"
        db.commit()
    except operator.OperatorError as e:
        vm.state = "error"
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"status": "started"}


@app.post("/vms/{vm_id}/actions/stop", status_code=status.HTTP_202_ACCEPTED)
def stop_vm(vm_id: str, db: Session = Depends(get_db)):
    vm = db.query(models.VM).filter(models.VM.id == vm_id).first()
    if not vm:
        raise HTTPException(status_code=404, detail="VM not found")
    
    if vm.state != "running":
        raise HTTPException(status_code=400, detail=f"VM is not running (current state: {vm.state})")
    
    try:
        _operator.stop_vm(vm_id, force=False)
        vm.state = "stopped"
        db.commit()
    except operator.OperatorError as e:
        vm.state = "error"
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"status": "stopped"}


@app.post("/vms/{vm_id}/actions/restart", status_code=status.HTTP_202_ACCEPTED)
def restart_vm(vm_id: str, db: Session = Depends(get_db)):
    vm = db.query(models.VM).filter(models.VM.id == vm_id).first()
    if not vm:
        raise HTTPException(status_code=404, detail="VM not found")
    
    # Stop if running
    if vm.state == "running":
        try:
            _operator.stop_vm(vm_id, force=False)
        except operator.OperatorError as e:
            raise HTTPException(status_code=400, detail=f"Failed to stop VM: {e}")
    
    # Start
    template = db.query(models.VMTemplate).filter(models.VMTemplate.name == vm.template_name).first()
    storage_path = Path(_operator.storage_path)
    vm_dir = storage_path / "vms" / vm_id
    qcow2_path = vm_dir / "root.qcow2" if (vm_dir / "root.qcow2").exists() else None
    
    try:
        _operator.start_vm(
            vm_id=vm_id,
            qcow2_path=qcow2_path,
            cpu_count=template.cpu_count,
            ram_gb=template.ram_amount
        )
        vm.state = "running"
        db.commit()
    except operator.OperatorError as e:
        vm.state = "error"
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"status": "restarted"}


# Disk endpoints
@app.post("/disks", response_model=schemas.Disk, status_code=status.HTTP_201_CREATED)
def create_disk(payload: schemas.DiskCreate, db: Session = Depends(get_db)):
    disk_id = str(uuid.uuid4())
    
    # Check if disk ID already exists (unlikely but possible)
    existing = db.query(models.Disk).filter(models.Disk.id == disk_id).first()
    if existing:
        disk_id = str(uuid.uuid4())  # Retry with new UUID
    
    # Create disk image
    storage_path = Path(_operator.storage_path)
    disk_path = storage_path / "disks" / f"{disk_id}.qcow2"
    
    try:
        _operator.create_disk_image(disk_path, payload.size)
    except operator.OperatorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Create disk in database
    disk = models.Disk(
        id=disk_id,
        size=payload.size,
        mount_point=payload.mount_point,
        state="available"
    )
    db.add(disk)
    db.commit()
    db.refresh(disk)
    
    return disk


@app.get("/disks", response_model=list[schemas.Disk])
def list_disks(db: Session = Depends(get_db)):
    disks = db.query(models.Disk).all()
    return disks


@app.get("/disks/{disk_id}", response_model=schemas.Disk)
def get_disk(disk_id: str, db: Session = Depends(get_db)):
    disk = db.query(models.Disk).filter(models.Disk.id == disk_id).first()
    if not disk:
        raise HTTPException(status_code=404, detail="Disk not found")
    return disk


@app.delete("/disks/{disk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_disk(disk_id: str, db: Session = Depends(get_db)):
    disk = db.query(models.Disk).filter(models.Disk.id == disk_id).first()
    if not disk:
        raise HTTPException(status_code=404, detail="Disk not found")
    
    if disk.state == "attached":
        raise HTTPException(status_code=400, detail="Cannot delete attached disk. Detach it first.")
    
    # Delete disk image
    storage_path = Path(_operator.storage_path)
    disk_path = storage_path / "disks" / f"{disk_id}.qcow2"
    
    try:
        _operator.delete_disk_image(disk_path)
    except operator.OperatorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    db.delete(disk)
    db.commit()
    return None


@app.post("/disks/{disk_id}/attach", status_code=status.HTTP_200_OK)
def attach_disk(disk_id: str, payload: dict, db: Session = Depends(get_db)):
    vm_id = payload.get("vm_id")
    if not vm_id:
        raise HTTPException(status_code=400, detail="vm_id is required")
    
    disk = db.query(models.Disk).filter(models.Disk.id == disk_id).first()
    if not disk:
        raise HTTPException(status_code=404, detail="Disk not found")
    
    if disk.state == "attached":
        raise HTTPException(status_code=400, detail="Disk is already attached")
    
    vm = db.query(models.VM).filter(models.VM.id == vm_id).first()
    if not vm:
        raise HTTPException(status_code=404, detail="VM not found")
    
    if vm.state != "running":
        raise HTTPException(status_code=400, detail="VM must be running to attach disk")
    
    # Get disk path
    storage_path = Path(_operator.storage_path)
    disk_path = storage_path / "disks" / f"{disk_id}.qcow2"
    
    # Determine mount point (use provided or auto-assign)
    mount_point = disk.mount_point or "/dev/xvdb"  # Default to xvdb if not specified
    
    try:
        _operator.attach_disk(vm_id, disk_path, device=mount_point)
        disk.vm_id = vm_id
        disk.state = "attached"
        disk.mount_point = mount_point
        db.commit()
    except operator.OperatorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"status": "attached"}


@app.post("/disks/{disk_id}/detach", status_code=status.HTTP_200_OK)
def detach_disk(disk_id: str, db: Session = Depends(get_db)):
    disk = db.query(models.Disk).filter(models.Disk.id == disk_id).first()
    if not disk:
        raise HTTPException(status_code=404, detail="Disk not found")
    
    if disk.state != "attached":
        raise HTTPException(status_code=400, detail="Disk is not attached")
    
    if not disk.vm_id:
        raise HTTPException(status_code=400, detail="Disk has no associated VM")
    
    vm = db.query(models.VM).filter(models.VM.id == disk.vm_id).first()
    if not vm or vm.state != "running":
        # VM not running or not found - just update database
        disk.vm_id = None
        disk.state = "available"
        disk.mount_point = None
        db.commit()
        return {"status": "detached"}
    
    # Get disk path
    storage_path = Path(_operator.storage_path)
    disk_path = storage_path / "disks" / f"{disk_id}.qcow2"
    
    try:
        _operator.detach_disk(disk.vm_id, disk_path)
        disk.vm_id = None
        disk.state = "available"
        disk.mount_point = None
        db.commit()
    except operator.OperatorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"status": "detached"}
