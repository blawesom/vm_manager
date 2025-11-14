from sqlalchemy import Column, Integer, String, ForeignKey
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

class Disk(Base):
    __tablename__ = "disks"
    id = Column(String, primary_key=True, index=True)
    size = Column(Integer, nullable=False)
    mount_point = Column(String, nullable=True)
    state = Column(String, nullable=False)
    vm_id = Column(String, ForeignKey("vms.id"), nullable=True)
