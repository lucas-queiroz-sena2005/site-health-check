from typing import Any
from fastapi import APIRouter

router = APIRouter(prefix="/schemas", tags=["schemas"])

@router.get("/schedule")
def get_schedule_schema() -> dict[str, Any]:
    # In a real app, this would be generated dynamically from Pydantic models (e.g. TaskFlags)
    # For MVP, we return a hardcoded JSON schema representing the flags the engine supports
    return {
        "title": "ScheduleFlags",
        "type": "object",
        "properties": {
            "check_http": {
                "type": "boolean",
                "title": "Check HTTP Routing",
                "default": True
            },
            "timeout_seconds": {
                "type": "integer",
                "title": "Timeout (seconds)",
                "default": 30
            }
        },
        "required": ["check_http", "timeout_seconds"]
    }
