from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db

router = APIRouter()

@router.post("/", response_model=schemas.ClientWorkspace)
def create_workspace(workspace: schemas.ClientWorkspaceCreate, db: Session = Depends(get_db)):
    db_workspace = models.ClientWorkspace(**workspace.model_dump())
    db.add(db_workspace)
    db.commit()
    db.refresh(db_workspace)
    return db_workspace

@router.get("/", response_model=List[schemas.ClientWorkspace])
def read_workspaces(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    workspaces = db.query(models.ClientWorkspace).offset(skip).limit(limit).all()
    return workspaces

@router.post("/{workspace_id}/environments", response_model=schemas.Environment)
def create_environment(workspace_id: int, env: schemas.EnvironmentCreate, db: Session = Depends(get_db)):
    db_env = models.Environment(**env.model_dump(), workspace_id=workspace_id)
    db.add(db_env)
    db.commit()
    db.refresh(db_env)
    return db_env

@router.get("/{workspace_id}/environments", response_model=List[schemas.Environment])
def read_environments(workspace_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    environments = db.query(models.Environment).filter(models.Environment.workspace_id == workspace_id).offset(skip).limit(limit).all()
    return environments
