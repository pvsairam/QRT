from fastapi import APIRouter, HTTPException
import subprocess
import os

router = APIRouter()

@router.post("/record")
def launch_recorder(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    try:
        # Launch playwright codegen non-blocking
        subprocess.Popen(["playwright", "codegen", url])
        return {"message": "Playwright recorder launched successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
