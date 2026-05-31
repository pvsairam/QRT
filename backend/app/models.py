from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

class ClientWorkspace(Base):
    __tablename__ = 'client_workspaces'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String)
    environments = relationship("Environment", back_populates="workspace", cascade="all, delete-orphan")

class Environment(Base):
    __tablename__ = 'environments'
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey('client_workspaces.id'))
    name = Column(String) # e.g., "DEV1", "TEST"
    base_url = Column(String)
    default_username = Column(String, nullable=True)
    default_password = Column(String, nullable=True)
    release_version = Column(String, nullable=True)
    workspace = relationship("ClientWorkspace", back_populates="environments")

class LLMProviderConfig(Base):
    __tablename__ = 'llm_provider_configs'
    id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String) # openai, anthropic, gemini
    api_key_masked = Column(String) # Masked version for display
    api_key_secret = Column(String) # Real key (in a real app, encrypted or in a vault)
    is_active = Column(Boolean, default=True)

class TestScript(Base):
    __tablename__ = 'test_scripts'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    module = Column(String)
    category = Column(String)
    version = Column(Integer, default=1)
    status = Column(String, default="Draft")
    raw_code = Column(Text, nullable=True)
    steps = relationship("TestStep", back_populates="script", cascade="all, delete-orphan")
    variables = relationship("TestVariable", back_populates="script", cascade="all, delete-orphan")

class TestStep(Base):
    __tablename__ = 'test_steps'
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey('test_scripts.id'))
    step_number = Column(Integer)
    action = Column(String)
    business_description = Column(String, nullable=True)
    target_name = Column(String, nullable=True)
    locator_strategy = Column(String, nullable=True)
    locator_value = Column(String, nullable=True)
    variable_name = Column(String, nullable=True)
    current_value = Column(String, nullable=True)
    is_sensitive = Column(Boolean, default=False)
    expected_result = Column(String, nullable=True)
    on_failure = Column(String, default="stop")
    notes = Column(Text, nullable=True)
    component_group = Column(String, nullable=True) # e.g., "Login Module"
    
    script = relationship("TestScript", back_populates="steps")

class TestVariable(Base):
    __tablename__ = 'test_variables'
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey('test_scripts.id'))
    name = Column(String)
    default_value = Column(String)
    
    script = relationship("TestScript", back_populates="variables")

class DataProfile(Base):
    __tablename__ = 'data_profiles'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    workspace_id = Column(Integer, ForeignKey('client_workspaces.id'))
    values = relationship("DataProfileValue", back_populates="profile", cascade="all, delete-orphan")

class DataProfileValue(Base):
    __tablename__ = 'data_profile_values'
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey('data_profiles.id'))
    variable_name = Column(String)
    actual_value = Column(String)
    
    profile = relationship("DataProfile", back_populates="values")

class ExecutionRun(Base):
    __tablename__ = 'execution_runs'
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey('test_scripts.id'))
    environment_id = Column(Integer, ForeignKey('environments.id'))
    data_profile_id = Column(Integer, ForeignKey('data_profiles.id'))
    status = Column(String) # Running, Passed, Failed
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    video_path = Column(String, nullable=True)
    trace_path = Column(String, nullable=True)
    
    script = relationship("TestScript")
    environment = relationship("Environment")
    data_profile = relationship("DataProfile")
    
    step_results = relationship("ExecutionStepResult", back_populates="run", cascade="all, delete-orphan")

class ExecutionStepResult(Base):
    __tablename__ = 'execution_step_results'
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey('execution_runs.id'))
    step_id = Column(Integer, ForeignKey('test_steps.id'))
    status = Column(String) # Passed, Failed, Skipped
    screenshot_path = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    
    run = relationship("ExecutionRun", back_populates="step_results")
    step = relationship("TestStep")
