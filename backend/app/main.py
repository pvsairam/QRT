import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from . import models
from .database import engine
from .api import scripts, workspaces, data_profiles, executions, upload, reports, tools
from .ui import pages

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Oracle Fusion Testing Platform API",
    description="API for managing and executing automated test scripts.",
    version="1.0.0"
)

# Configure CORS for local Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(workspaces.router, prefix="/api/workspaces", tags=["workspaces"])
app.include_router(data_profiles.router, prefix="/api/data-profiles", tags=["data profiles"])
app.include_router(executions.router, prefix="/api/executions", tags=["executions"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(tools.router, prefix="/api/tools", tags=["tools"])

app.include_router(pages.router, prefix="/ui", tags=["ui"])

app.mount("/static", StaticFiles(directory="app/static"), name="static")

os.makedirs("data", exist_ok=True)
app.mount("/data", StaticFiles(directory="data"), name="data")

@app.get("/")
def read_root(request: Request):
    return RedirectResponse(url="/ui/dashboard")
