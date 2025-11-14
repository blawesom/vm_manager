from pydantic import BaseModel, Field, constr
from typing import Optional

class VMTemplateCreate(BaseModel):
    name: constr(min_length=1)
    cpu_count: int = Field(..., ge=1)
    ram_amount: int = Field(..., ge=1)

class VMTemplate(BaseModel):
    name: str
    cpu_count: int
    ram_amount: int

    class Config:
        from_attributes = True

class VMCreate(BaseModel):
    template_name: str
    name: Optional[str] = None

class VM(BaseModel):
    id: str
    vm_template: VMTemplate
    state: str
    local_ip: Optional[str]

    class Config:
        from_attributes = True

class DiskCreate(BaseModel):
    size: int = Field(..., ge=1)
    mount_point: Optional[str] = None

class Disk(BaseModel):
    id: str
    size: int
    mount_point: Optional[str]
    state: str

    class Config:
        from_attributes = True
