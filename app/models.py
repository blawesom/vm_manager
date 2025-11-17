from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class VMTemplate(Base):
    __tablename__ = "vm_templates"
    name = Column(String, primary_key=True, index=True)
    cpu_count = Column(Integer, nullable=False)
    ram_amount = Column(Integer, nullable=False)

class VM(Base):
    __tablename__ = "vms"
    id = Column(String, primary_key=True, index=True)
    template_name = Column(String, ForeignKey("vm_templates.name"))
    state = Column(String, nullable=False)
    local_ip = Column(String, nullable=True)
    metadata = relationship("VMMetadata", back_populates="vm", uselist=False, cascade="all, delete-orphan")

class Disk(Base):
    __tablename__ = "disks"
    id = Column(String, primary_key=True, index=True)
    size = Column(Integer, nullable=False)
    mount_point = Column(String, nullable=True)
    state = Column(String, nullable=False)
    vm_id = Column(String, ForeignKey("vms.id"), nullable=True)

class VMMetadata(Base):
    __tablename__ = "vm_metadata"
    vm_id = Column(String, ForeignKey("vms.id"), primary_key=True, index=True)
    hostname = Column(String, nullable=True)
    user_data = Column(Text, nullable=True)  # cloud-init user-data script
    ssh_keys = Column(Text, nullable=True)  # newline-separated SSH public keys
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    vm = relationship("VM", back_populates="metadata")
