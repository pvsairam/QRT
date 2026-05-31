from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import csv
import io
from typing import List
from .. import schemas

router = APIRouter()

@router.post("/csv", response_model=List[schemas.TestStepBase])
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported for now")
        
    content = await file.read()
    try:
        decoded = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(decoded))
        
        steps = []
        for index, row in enumerate(reader):
            # Expecting columns: Action, Description, Target, Locator Strategy, Locator Value, Variable, Current Value, Expected
            step = schemas.TestStepBase(
                step_number=index + 1,
                action=row.get("Action", "click").lower(),
                business_description=row.get("Description", ""),
                target_name=row.get("Target", ""),
                locator_strategy=row.get("Locator Strategy", ""),
                locator_value=row.get("Locator Value", ""),
                variable_name=row.get("Variable", "").strip("{}"), # Remove {} if present
                current_value=row.get("Current Value", ""),
                expected_result=row.get("Expected", ""),
                on_failure="stop"
            )
            steps.append(step)
            
        return steps
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")
