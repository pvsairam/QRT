from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

# Common schemas
class EnvironmentBase(BaseModel):
    name: str
    base_url: Optional[str] = None
    default_username: Optional[str] = None
    default_password: Optional[str] = None
    release_version: Optional[str] = None

class EnvironmentCreate(EnvironmentBase):
    pass

class Environment(EnvironmentBase):
    id: int
    workspace_id: int
    model_config = ConfigDict(from_attributes=True)

class ClientWorkspaceBase(BaseModel):
    name: str
    description: Optional[str] = None

class ClientWorkspaceCreate(ClientWorkspaceBase):
    pass

class ClientWorkspace(ClientWorkspaceBase):
    id: int
    environments: List[Environment] = []
    model_config = ConfigDict(from_attributes=True)

class TestVariableBase(BaseModel):
    name: str
    default_value: Optional[str] = None

class TestVariableCreate(TestVariableBase):
    pass

class TestVariable(TestVariableBase):
    id: int
    script_id: int
    model_config = ConfigDict(from_attributes=True)

class TestStepBase(BaseModel):
    step_number: int
    action: str
    business_description: Optional[str] = None
    target_name: Optional[str] = None
    locator_strategy: Optional[str] = None
    locator_value: Optional[str] = None
    variable_name: Optional[str] = None
    current_value: Optional[str] = None
    is_sensitive: bool = False
    expected_result: Optional[str] = None
    on_failure: str = "stop"
    notes: Optional[str] = None

class TestStepCreate(TestStepBase):
    pass

class TestStep(TestStepBase):
    id: int
    script_id: int
    model_config = ConfigDict(from_attributes=True)

class TestScriptBase(BaseModel):
    name: str
    description: Optional[str] = None
    module: Optional[str] = None
    category: Optional[str] = None
    version: int = 1
    status: str = "Draft"

class TestScriptCreate(TestScriptBase):
    pass

class TestScript(TestScriptBase):
    id: int
    steps: List[TestStep] = []
    variables: List[TestVariable] = []
    model_config = ConfigDict(from_attributes=True)
    
class DataProfileValueBase(BaseModel):
    variable_name: str
    actual_value: str

class DataProfileValueCreate(DataProfileValueBase):
    pass

class DataProfileValue(DataProfileValueBase):
    id: int
    profile_id: int
    model_config = ConfigDict(from_attributes=True)
    
class DataProfileBase(BaseModel):
    name: str
    workspace_id: int

class DataProfileCreate(DataProfileBase):
    pass

class DataProfile(DataProfileBase):
    id: int
    values: List[DataProfileValue] = []
    model_config = ConfigDict(from_attributes=True)
