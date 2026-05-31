from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .. import models
from ..database import get_db
import subprocess
import os
import sys
import tempfile
import re
import io
import pandas as pd
from ..services import ai_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(request: Request, db: Session = Depends(get_db)):
    script_count = db.query(models.TestScript).count()
    workspace_count = db.query(models.ClientWorkspace).count()
    recent_executions = db.query(models.ExecutionRun).order_by(models.ExecutionRun.started_at.desc()).limit(5).all()
    
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "script_count": script_count,
            "workspace_count": workspace_count,
            "recent_executions": recent_executions
        }
    )

@router.get("/workspaces", response_class=HTMLResponse)
def get_workspaces(request: Request, db: Session = Depends(get_db)):
    workspaces = db.query(models.ClientWorkspace).all()
    return templates.TemplateResponse(
        request=request,
        name="workspaces.html",
        context={
            "request": request,
            "workspaces": workspaces
        }
    )

@router.post("/workspaces")
def create_workspace(request: Request, name: str = Form(...), description: str = Form(""), db: Session = Depends(get_db)):
    new_ws = models.ClientWorkspace(name=name, description=description)
    db.add(new_ws)
    db.commit()
    return RedirectResponse(url="/ui/workspaces", status_code=303)

@router.post("/workspaces/{workspace_id}/delete")
def delete_workspace(workspace_id: int, db: Session = Depends(get_db)):
    workspace = db.query(models.ClientWorkspace).filter(models.ClientWorkspace.id == workspace_id).first()
    if workspace:
        db.delete(workspace)
        db.commit()
    return RedirectResponse(url="/ui/workspaces", status_code=303)

@router.post("/workspaces/{workspace_id}/edit")
def edit_workspace(workspace_id: int, name: str = Form(...), description: str = Form(""), db: Session = Depends(get_db)):
    workspace = db.query(models.ClientWorkspace).filter(models.ClientWorkspace.id == workspace_id).first()
    if workspace:
        workspace.name = name
        workspace.description = description
        db.commit()
    return RedirectResponse(url="/ui/workspaces", status_code=303)

@router.post("/workspaces/{workspace_id}/environments")
def create_environment(
    workspace_id: int, 
    name: str = Form(...), 
    base_url: str = Form(""),
    default_username: str = Form(""),
    default_password: str = Form(""),
    release_version: str = Form(""),
    db: Session = Depends(get_db)
):
    new_env = models.Environment(
        name=name, 
        base_url=base_url, 
        workspace_id=workspace_id,
        default_username=default_username if default_username else None,
        default_password=default_password if default_password else None,
        release_version=release_version if release_version else None
    )
    db.add(new_env)
    db.commit()
    return RedirectResponse(url="/ui/workspaces", status_code=303)

@router.post("/workspaces/{workspace_id}/environments/{env_id}/edit")
def edit_environment(
    workspace_id: int, 
    env_id: int,
    name: str = Form(...), 
    base_url: str = Form(""),
    default_username: str = Form(""),
    default_password: str = Form(""),
    release_version: str = Form(""),
    db: Session = Depends(get_db)
):
    env = db.query(models.Environment).filter(models.Environment.id == env_id).first()
    if env:
        env.name = name
        env.base_url = base_url
        env.default_username = default_username if default_username else None
        if default_password: # Only update password if provided
            env.default_password = default_password
        env.release_version = release_version if release_version else None
        db.commit()
    return RedirectResponse(url="/ui/workspaces", status_code=303)

@router.post("/workspaces/{workspace_id}/environments/{env_id}/delete")
def delete_environment(workspace_id: int, env_id: int, db: Session = Depends(get_db)):
    env = db.query(models.Environment).filter(models.Environment.id == env_id).first()
    if env:
        db.delete(env)
        db.commit()
    return RedirectResponse(url="/ui/workspaces", status_code=303)

@router.get("/scripts", response_class=HTMLResponse)
def get_scripts(request: Request, db: Session = Depends(get_db)):
    scripts = db.query(models.TestScript).all()
    return templates.TemplateResponse(
        request=request,
        name="scripts.html",
        context={
            "request": request,
            "scripts": scripts
        }
    )

@router.post("/scripts")
def create_script(request: Request, name: str = Form(...), description: str = Form(""), category: str = Form(""), db: Session = Depends(get_db)):
    new_script = models.TestScript(name=name, description=description, category=category)
    db.add(new_script)
    db.commit()
    return RedirectResponse(url="/ui/scripts", status_code=303)

@router.post("/scripts/{script_id}/delete")
def delete_script(script_id: int, db: Session = Depends(get_db)):
    script = db.query(models.TestScript).filter(models.TestScript.id == script_id).first()
    if script:
        db.delete(script)
        db.commit()
    return RedirectResponse(url="/ui/scripts", status_code=303)

@router.post("/scripts/{script_id}/edit")
def edit_script(script_id: int, name: str = Form(...), description: str = Form(""), category: str = Form(""), db: Session = Depends(get_db)):
    script = db.query(models.TestScript).filter(models.TestScript.id == script_id).first()
    if script:
        script.name = name
        script.description = description
        script.category = category
        db.commit()
    return RedirectResponse(url="/ui/scripts", status_code=303)

@router.post("/scripts/{script_id}/record")
def record_script(script_id: int, background_tasks: BackgroundTasks, environment_id: int = Form(...), db: Session = Depends(get_db)):
    env = db.query(models.Environment).filter(models.Environment.id == environment_id).first()
    if env and env.base_url:
        def run_and_parse():
            file_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp_file:
                    file_path = tmp_file.name
                
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.run([sys.executable, "-m", "playwright", "codegen", env.base_url, "-o", file_path], creationflags=creationflags)
                
                with next(get_db()) as db_session:
                    script = db_session.query(models.TestScript).filter(models.TestScript.id == script_id).first()
                    if script and os.path.exists(file_path):
                        with open(file_path, "r") as f:
                            code = f.read()
                        
                        import urllib.parse as urlparse
                        parsed_base = urlparse.urlparse(env.base_url)
                        base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
                        
                        import re
                        code = code.replace(base_origin, '{base_url}')
                        code = re.sub(r'(name="Username"\)\.fill\(")[^"]+("\))', r'\g<1>{Username}\g<2>', code, flags=re.IGNORECASE)
                        code = re.sub(r'(name="Password"\)\.fill\(")[^"]+("\))', r'\g<1>{Password}\g<2>', code, flags=re.IGNORECASE)
                        
                        script.raw_code = code
                        db_session.commit()
                        
                        # Use AI to parse the steps
                        active_provider = db_session.query(models.LLMProviderConfig).filter(models.LLMProviderConfig.is_active == True).first()
                        if active_provider:
                            try:
                                ai_steps = ai_service.generate_steps_from_text(code, active_provider)
                                for step_data in ai_steps:
                                    new_step = models.TestStep(
                                        script_id=script.id,
                                        step_number=len(script.steps) + 1,
                                        action=step_data.get("action", "unknown"),
                                        business_description=step_data.get("business_description", ""),
                                        target_name=step_data.get("target_name", ""),
                                        locator_strategy=step_data.get("locator_strategy", ""),
                                        locator_value=step_data.get("locator_value", ""),
                                        variable_name=step_data.get("variable_name", ""),
                                        current_value=step_data.get("current_value", ""),
                                        expected_result=step_data.get("expected_result", ""),
                                        is_sensitive=step_data.get("is_sensitive", False),
                                        on_failure=step_data.get("on_failure", "stop")
                                    )
                                    db_session.add(new_step)
                                    db_session.commit()
                            except Exception as e:
                                print(f"AI Step Generation failed: {e}")
                        else:
                            # Fallback: Basic parser if no AI configured
                            lines = code.split('\n')
                            step_number = 1
                            has_navigated = False
                            for line in lines:
                                line = line.strip()
                                if line.startswith("page.goto("):
                                    url = line.split("page.goto(")[1].split(")")[0].strip("\"'")
                                    
                                    import urllib.parse as urlparse
                                    parsed = urlparse.urlparse(url)
                                    query_params = urlparse.parse_qs(parsed.query, keep_blank_values=True)
                                    for p in ['_adf.ctrl-state', '_afrLoop', '_afrWindowMode', '_afrWindowId', '_afrFS', '_afrMT', '_afrMFW', '_afrMFH', '_afrMFDW', '_afrMFDH', '_afrMFC', '_afrMFCI', '_afrMFM', '_afrMFR', '_afrMFG', '_afrMFS', '_afrMFO']:
                                        query_params.pop(p, None)
                                    url = urlparse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlparse.urlencode(query_params, doseq=True), parsed.fragment))
                                    
                                    if env.base_url:
                                        import urllib.parse as urlparse
                                        parsed_base = urlparse.urlparse(env.base_url)
                                        base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
                                        
                                        if url.startswith(base_origin):
                                            url = url.replace(base_origin, "{base_url}")
                                        elif not has_navigated:
                                            url = "{base_url}"
                                        
                                    has_navigated = True
                                    new_step = models.TestStep(
                                        script_id=script.id,
                                        step_number=step_number,
                                        action="Navigate",
                                        business_description=f"Navigate to {url}",
                                        locator_value=url,
                                        expected_result="Page loaded"
                                    )
                                    db_session.add(new_step)
                                    step_number += 1
                                elif ".click()" in line and "page." in line:
                                    locator = line.split(".click()")[0].replace("page.locator(", "").replace("page.get_by_role(", "").strip()
                                    new_step = models.TestStep(
                                        script_id=script.id,
                                        step_number=step_number,
                                        action="Click",
                                        business_description="Click element",
                                        locator_value=locator,
                                        expected_result="Element clicked"
                                    )
                                    db_session.add(new_step)
                                    step_number += 1
                                elif ".fill(" in line and "page." in line:
                                    locator = line.split(".fill(")[0].replace("page.locator(", "").replace("page.get_by_role(", "").strip()
                                    val = line.split(".fill(")[1].split(")")[0].strip("\"'")
                                    new_step = models.TestStep(
                                        script_id=script.id,
                                        step_number=step_number,
                                        action="Input",
                                        business_description="Fill input",
                                        locator_value=locator,
                                        current_value=val,
                                        expected_result="Input filled"
                                    )
                                    db_session.add(new_step)
                                    step_number += 1
                            db_session.commit()
            except Exception as e:
                print(f"Background recording failed: {e}")
            finally:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass

        background_tasks.add_task(run_and_parse)
        
    return RedirectResponse(url=f"/ui/scripts/{script_id}", status_code=303)

@router.get("/scripts/{script_id}", response_class=HTMLResponse)
def get_script_detail(request: Request, script_id: int, db: Session = Depends(get_db)):
    script = db.query(models.TestScript).filter(models.TestScript.id == script_id).first()
    data_profiles = db.query(models.DataProfile).all()
    environments = db.query(models.Environment).all()
    return templates.TemplateResponse(
        request=request,
        name="script_detail.html",
        context={
            "request": request,
            "script": script,
            "data_profiles": data_profiles,
            "environments": environments
        }
    )

@router.get("/data-profiles", response_class=HTMLResponse)
def get_data_profiles(request: Request, db: Session = Depends(get_db)):
    profiles = db.query(models.DataProfile).all()
    workspaces = db.query(models.ClientWorkspace).all()
    return templates.TemplateResponse(
        request=request,
        name="data_profiles.html",
        context={
            "request": request,
            "profiles": profiles,
            "workspaces": workspaces
        }
    )

@router.post("/data-profiles")
def create_data_profile(request: Request, name: str = Form(...), workspace_id: int = Form(...), db: Session = Depends(get_db)):
    new_profile = models.DataProfile(name=name, workspace_id=workspace_id)
    db.add(new_profile)
    db.commit()
    return RedirectResponse(url="/ui/data-profiles", status_code=303)

@router.post("/scripts/{script_id}/steps")
def add_script_step(
    request: Request,
    script_id: int,
    step_number: int = Form(...),
    action: str = Form(...),
    business_description: str = Form(""),
    target_name: str = Form(""),
    locator_strategy: str = Form(""),
    locator_value: str = Form(""),
    variable_name: str = Form(""),
    current_value: str = Form(""),
    expected_result: str = Form(""),
    component_group: str = Form(""),
    db: Session = Depends(get_db)
):
    # Auto-adjust: If step_number exists, bump it and all subsequent steps down by 1
    existing_step = db.query(models.TestStep).filter(
        models.TestStep.script_id == script_id, 
        models.TestStep.step_number == step_number
    ).first()
    
    if existing_step:
        # Get all steps >= this number, ordered descending to avoid unique constraint violations if any
        subsequent_steps = db.query(models.TestStep).filter(
            models.TestStep.script_id == script_id,
            models.TestStep.step_number >= step_number
        ).order_by(models.TestStep.step_number.desc()).all()
        
        for s in subsequent_steps:
            s.step_number += 1
        db.commit()

    new_step = models.TestStep(
        script_id=script_id,
        step_number=step_number,
        action=action,
        business_description=business_description,
        target_name=target_name,
        locator_strategy=locator_strategy,
        locator_value=locator_value,
        variable_name=variable_name,
        current_value=current_value,
        expected_result=expected_result,
        component_group=component_group
    )
    db.add(new_step)
    db.commit()
    return RedirectResponse(url=f"/ui/scripts/{script_id}", status_code=303)

@router.post("/scripts/{script_id}/steps/{step_id}/delete")
def delete_step(script_id: int, step_id: int, db: Session = Depends(get_db)):
    step = db.query(models.TestStep).filter(models.TestStep.id == step_id).first()
    if step:
        db.delete(step)
        db.commit()
    return RedirectResponse(url=f"/ui/scripts/{script_id}", status_code=303)

@router.post("/scripts/{script_id}/steps/{step_id}/edit")
def edit_script_step(
    script_id: int,
    step_id: int,
    step_number: int = Form(...),
    action: str = Form(...),
    business_description: str = Form(""),
    target_name: str = Form(""),
    locator_strategy: str = Form(""),
    locator_value: str = Form(""),
    variable_name: str = Form(""),
    current_value: str = Form(""),
    expected_result: str = Form(""),
    component_group: str = Form(""),
    db: Session = Depends(get_db)
):
    step = db.query(models.TestStep).filter(models.TestStep.id == step_id).first()
    if step:
        if step.step_number != step_number:
            # Auto-adjust if editing to an existing step number
            existing_step = db.query(models.TestStep).filter(
                models.TestStep.script_id == script_id,
                models.TestStep.step_number == step_number
            ).first()
            if existing_step:
                subsequent_steps = db.query(models.TestStep).filter(
                    models.TestStep.script_id == script_id,
                    models.TestStep.step_number >= step_number,
                    models.TestStep.id != step.id
                ).order_by(models.TestStep.step_number.desc()).all()
                for s in subsequent_steps:
                    s.step_number += 1
                db.commit()

        step.step_number = step_number
        step.action = action
        step.business_description = business_description
        step.target_name = target_name
        step.locator_strategy = locator_strategy
        step.locator_value = locator_value
        step.variable_name = variable_name
        step.current_value = current_value
        step.expected_result = expected_result
        step.component_group = component_group
        db.commit()
    return RedirectResponse(url=f"/ui/scripts/{script_id}", status_code=303)

@router.get("/data-profiles/{profile_id}", response_class=HTMLResponse)
def get_data_profile_detail(request: Request, profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(models.DataProfile).filter(models.DataProfile.id == profile_id).first()
    return templates.TemplateResponse(
        request=request,
        name="data_profile_detail.html",
        context={
            "request": request,
            "profile": profile
        }
    )

@router.post("/data-profiles/{profile_id}/values")
def add_data_profile_value(
    request: Request,
    profile_id: int,
    variable_name: str = Form(...),
    actual_value: str = Form(...),
    db: Session = Depends(get_db)
):
    new_val = models.DataProfileValue(
        profile_id=profile_id,
        variable_name=variable_name,
        actual_value=actual_value
    )
    db.add(new_val)
    db.commit()
    return RedirectResponse(url=f"/ui/data-profiles/{profile_id}", status_code=303)

@router.post("/data-profiles/{profile_id}/values/{value_id}/delete")
def delete_data_profile_value(profile_id: int, value_id: int, db: Session = Depends(get_db)):
    val = db.query(models.DataProfileValue).filter(models.DataProfileValue.id == value_id).first()
    if val:
        db.delete(val)
        db.commit()
    return RedirectResponse(url=f"/ui/data-profiles/{profile_id}", status_code=303)

@router.post("/data-profiles/{profile_id}/delete")
def delete_data_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(models.DataProfile).filter(models.DataProfile.id == profile_id).first()
    if profile:
        db.delete(profile)
        db.commit()
    return RedirectResponse(url="/ui/data-profiles", status_code=303)

@router.post("/data-profiles/{profile_id}/edit")
def edit_data_profile(profile_id: int, name: str = Form(...), workspace_id: int = Form(...), db: Session = Depends(get_db)):
    profile = db.query(models.DataProfile).filter(models.DataProfile.id == profile_id).first()
    if profile:
        profile.name = name
        profile.workspace_id = workspace_id
        db.commit()
    return RedirectResponse(url="/ui/data-profiles", status_code=303)

@router.post("/data-profiles/{profile_id}/values/{value_id}/edit")
def edit_data_profile_value(profile_id: int, value_id: int, variable_name: str = Form(...), actual_value: str = Form(...), db: Session = Depends(get_db)):
    val = db.query(models.DataProfileValue).filter(models.DataProfileValue.id == value_id).first()
    if val:
        val.variable_name = variable_name
        val.actual_value = actual_value
        db.commit()
    return RedirectResponse(url=f"/ui/data-profiles/{profile_id}", status_code=303)

# ----------------- Settings & AI ----------------- #

@router.get("/settings", response_class=HTMLResponse)
def get_settings(request: Request, db: Session = Depends(get_db)):
    providers = db.query(models.LLMProviderConfig).all()
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "request": request,
            "providers": providers
        }
    )

@router.post("/settings/llm")
def add_llm_provider(
    provider_name: str = Form(...),
    api_key_secret: str = Form(...),
    is_active: bool = Form(False),
    db: Session = Depends(get_db)
):
    if is_active:
        # Deactivate others
        db.query(models.LLMProviderConfig).update({"is_active": False})
        
    api_key_masked = api_key_secret[:4] + "*" * 10 + api_key_secret[-4:] if len(api_key_secret) > 8 else "***"
    
    provider = models.LLMProviderConfig(
        provider_name=provider_name,
        api_key_secret=api_key_secret,
        api_key_masked=api_key_masked,
        is_active=is_active
    )
    db.add(provider)
    db.commit()
    return RedirectResponse(url="/ui/settings", status_code=303)

@router.post("/settings/llm/{provider_id}/delete")
def delete_llm_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(models.LLMProviderConfig).filter(models.LLMProviderConfig.id == provider_id).first()
    if provider:
        db.delete(provider)
        db.commit()
    return RedirectResponse(url="/ui/settings", status_code=303)

@router.post("/settings/llm/{provider_id}/activate")
def activate_llm_provider(provider_id: int, db: Session = Depends(get_db)):
    db.query(models.LLMProviderConfig).update({"is_active": False})
    provider = db.query(models.LLMProviderConfig).filter(models.LLMProviderConfig.id == provider_id).first()
    if provider:
        provider.is_active = True
        db.commit()
    return RedirectResponse(url="/ui/settings", status_code=303)

# ----------------- Upload Generation ----------------- #

@router.post("/scripts/{script_id}/upload")
async def upload_script_file(
    script_id: int, 
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    environment_id: int = Form(...),
    db: Session = Depends(get_db)
):
    script = db.query(models.TestScript).filter(models.TestScript.id == script_id).first()
    if not script:
        return RedirectResponse(url="/ui/scripts", status_code=303)
        
    content = await file.read()
    filename = file.filename.lower()
    text_content = ""
    
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
            text_content = df.to_string()
        elif filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(io.BytesIO(content))
            text_content = df.to_string()
        elif filename.endswith((".json", ".txt", ".md")):
            text_content = content.decode("utf-8")
        else:
            print("Unsupported file format for upload")
            return RedirectResponse(url=f"/ui/scripts/{script_id}", status_code=303)
            
        active_provider = db.query(models.LLMProviderConfig).filter(models.LLMProviderConfig.is_active == True).first()
        if active_provider and text_content:
            from ..services import ai_agent
            # Mark script state as generating (we can use a flash message for now)
            background_tasks.add_task(
                ai_agent.run_autonomous_recording,
                script_id,
                text_content,
                environment_id,
                active_provider
            )
            return RedirectResponse(url=f"/ui/scripts/{script_id}?success=Agent+started+autonomous+generation+in+the+background.+Please+refresh+to+see+steps+as+they+appear.", status_code=303)
    except Exception as e:
        print(f"Failed to process upload: {e}")
        import urllib.parse
        error_msg = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/ui/scripts/{script_id}?error={error_msg}", status_code=303)
        
    return RedirectResponse(url=f"/ui/scripts/{script_id}", status_code=303)

# ----------------- Execution History & Evidence ----------------- #

@router.get("/executions", response_class=HTMLResponse)
def get_executions(request: Request, db: Session = Depends(get_db)):
    executions = db.query(models.ExecutionRun).order_by(models.ExecutionRun.started_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="executions.html",
        context={
            "request": request,
            "executions": executions
        }
    )

@router.get("/executions/{run_id}", response_class=HTMLResponse)
def get_execution_detail(request: Request, run_id: int, db: Session = Depends(get_db)):
    run = db.query(models.ExecutionRun).filter(models.ExecutionRun.id == run_id).first()
    return templates.TemplateResponse(
        request=request,
        name="execution_detail.html",
        context={
            "request": request,
            "run": run
        }
    )

