from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from .. import models, schemas
from ..database import get_db, SessionLocal
from ..services.executor import PlaywrightExecutor

router = APIRouter()

class RunRequest(BaseModel):
    script_id: int
    environment_id: int
    data_profile_id: Optional[int] = None
    headless: bool = False
    record_video: bool = False
    collect_trace: bool = False
    screenshots: str = "on_failure"
    run_mode: str = "structured"

def background_execution(run_id: int, script_id: int, data_profile_id: Optional[int], env_id: int, 
                         headless: bool, record_video: bool, collect_trace: bool, screenshots: str, run_mode: str):
    db = SessionLocal()
    try:
        script = db.query(models.TestScript).filter(models.TestScript.id == script_id).first()
        data_profile = None
        if data_profile_id:
            data_profile = db.query(models.DataProfile).filter(models.DataProfile.id == data_profile_id).first()
        env = db.query(models.Environment).filter(models.Environment.id == env_id).first()
        
        executor = PlaywrightExecutor(db, run_id)
        executor.execute_script(script, data_profile.values if data_profile else [], env, 
                                headless, record_video, collect_trace, screenshots, run_mode)
    finally:
        db.close()

@router.post("/run", response_model=dict)
def run_script(req: RunRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Verify script, data profile, and environment exist
    script = db.query(models.TestScript).filter(models.TestScript.id == req.script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
        
    dp_values = []
    if req.data_profile_id:
        data_profile = db.query(models.DataProfile).filter(models.DataProfile.id == req.data_profile_id).first()
        if not data_profile:
            raise HTTPException(status_code=404, detail="Data Profile not found")
        dp_values = data_profile.values
        
    env = db.query(models.Environment).filter(models.Environment.id == req.environment_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
        
    run_record = models.ExecutionRun(
        script_id=req.script_id,
        environment_id=req.environment_id,
        data_profile_id=req.data_profile_id,
        status="Pending"
    )
    db.add(run_record)
    db.commit()
    db.refresh(run_record)
    
    background_tasks.add_task(
        background_execution, 
        run_record.id, 
        req.script_id, 
        req.data_profile_id, 
        req.environment_id,
        req.headless,
        req.record_video,
        req.collect_trace,
        req.screenshots,
        req.run_mode
    )
    
    return {"message": "Execution started", "run_id": run_record.id}

@router.post("/run-sync", response_model=dict)
def run_script_sync(req: RunRequest, db: Session = Depends(get_db)):
    # Verify script, data profile, and environment exist
    script = db.query(models.TestScript).filter(models.TestScript.id == req.script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
        
    dp_values = []
    if req.data_profile_id:
        data_profile = db.query(models.DataProfile).filter(models.DataProfile.id == req.data_profile_id).first()
        if not data_profile:
            raise HTTPException(status_code=404, detail="Data Profile not found")
        dp_values = data_profile.values
        
    env = db.query(models.Environment).filter(models.Environment.id == req.environment_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
        
    run_record = models.ExecutionRun(
        script_id=req.script_id,
        environment_id=req.environment_id,
        data_profile_id=req.data_profile_id,
        status="Pending"
    )
    db.add(run_record)
    db.commit()
    db.refresh(run_record)
    
    executor = PlaywrightExecutor(db, run_record.id)
    executor.execute_script(script, dp_values, env, req.headless, req.record_video, req.collect_trace, req.screenshots, req.run_mode)
    
    return {"message": "Execution completed", "run_id": run_record.id}

@router.post("/{run_id}/cancel")
def cancel_execution(run_id: int, db: Session = Depends(get_db)):
    run = db.query(models.ExecutionRun).filter(models.ExecutionRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    if run.status in ["Passed", "Failed", "Cancelled"]:
        return {"status": "Already finished"}
        
    run.status = "Cancelled"
    db.commit()
    return {"status": "Cancelled"}

@router.get("/{run_id}/status")
def get_execution_status(run_id: int, db: Session = Depends(get_db)):
    run = db.query(models.ExecutionRun).filter(models.ExecutionRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    steps = []
    for sr in sorted(run.step_results, key=lambda s: s.step.step_number if s.step else 0):
        target_val = ""
        if sr.step:
            target_val = sr.step.target_name or sr.step.locator_value or ""
            
        steps.append({
            "step_number": sr.step.step_number if sr.step else "?",
            "action": sr.step.action if sr.step else "Raw Execution",
            "target": target_val,
            "status": sr.status,
            "error": sr.error_message
        })
        
    return {
        "run_id": run.id,
        "status": run.status,
        "steps": steps
    }
