from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class VMTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1)
    cpu_count: int = Field(..., ge=1)
    ram_amount: int = Field(..., ge=1)

class VMTemplate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    name: str
    cpu_count: int
    ram_amount: int

class VMCreate(BaseModel):
    template_name: str
    name: Optional[str] = None

class VM(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    vm_template: VMTemplate
    state: str
    local_ip: Optional[str]

class DiskCreate(BaseModel):
    size: int = Field(..., ge=1)
    mount_point: Optional[str] = None

class Disk(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    size: int
    mount_point: Optional[str]
    state: str

class VMConsole(BaseModel):
    vm_id: str
    console: str
    size: int
    file_size: Optional[int] = None
    message: Optional[str] = None

class VMMetadataCreate(BaseModel):
    hostname: Optional[str] = None
    user_data: Optional[str] = None  # cloud-init user-data script
    ssh_keys: Optional[str] = None  # newline-separated SSH public keys

class VMMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    vm_id: str
    hostname: Optional[str]
    user_data: Optional[str]
    ssh_keys: Optional[str]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
