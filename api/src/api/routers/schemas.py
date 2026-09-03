from typing import Any
from fastapi import APIRouter
from api.models import ExecutionConfig

router = APIRouter(prefix="/schemas", tags=["schemas"])

@router.get("/schedule")
def get_schedule_schema() -> dict[str, Any]:
    # Dynamically generated JSON schema from the ExecutionConfig model
    return ExecutionConfig.model_json_schema()
