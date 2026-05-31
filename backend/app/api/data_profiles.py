from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db

router = APIRouter()

@router.post("/", response_model=schemas.DataProfile)
def create_data_profile(profile: schemas.DataProfileCreate, db: Session = Depends(get_db)):
    db_profile = models.DataProfile(**profile.model_dump())
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return db_profile

@router.get("/", response_model=List[schemas.DataProfile])
def read_data_profiles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    profiles = db.query(models.DataProfile).offset(skip).limit(limit).all()
    return profiles

@router.post("/{profile_id}/values", response_model=schemas.DataProfileValue)
def create_data_profile_value(profile_id: int, value: schemas.DataProfileValueCreate, db: Session = Depends(get_db)):
    db_value = models.DataProfileValue(**value.model_dump(), profile_id=profile_id)
    db.add(db_value)
    db.commit()
    db.refresh(db_value)
    return db_value
