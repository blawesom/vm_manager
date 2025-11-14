from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from . import db, models, schemas
from sqlalchemy.orm import Session
from fastapi import status
import pathlib
import uuid

app = FastAPI(title="VMAN INTEL (stub)", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db_session = db.SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


@app.on_event("startup")
def startup_event():
    # create tables
    models.Base.metadata.create_all(bind=db.engine)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


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
    db.delete(tpl)
    db.commit()
    return None
