from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db

router = APIRouter()

@router.post("/", response_model=schemas.TestScript)
def create_script(script: schemas.TestScriptCreate, db: Session = Depends(get_db)):
    db_script = models.TestScript(**script.model_dump())
    db.add(db_script)
    db.commit()
    db.refresh(db_script)
    return db_script

@router.get("/", response_model=List[schemas.TestScript])
def read_scripts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    scripts = db.query(models.TestScript).offset(skip).limit(limit).all()
    return scripts

@router.get("/{script_id}", response_model=schemas.TestScript)
def read_script(script_id: int, db: Session = Depends(get_db)):
    script = db.query(models.TestScript).filter(models.TestScript.id == script_id).first()
    if script is None:
        raise HTTPException(status_code=404, detail="Script not found")
    return script
    
@router.post("/{script_id}/steps", response_model=schemas.TestStep)
def create_step(script_id: int, step: schemas.TestStepCreate, db: Session = Depends(get_db)):
    db_script = db.query(models.TestScript).filter(models.TestScript.id == script_id).first()
    if not db_script:
         raise HTTPException(status_code=404, detail="Script not found")
    db_step = models.TestStep(**step.model_dump(), script_id=script_id)
    db.add(db_step)
    db.commit()
    db.refresh(db_step)
    return db_step
