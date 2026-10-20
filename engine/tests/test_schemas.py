import pytest
from pydantic import BaseModel


def test_task_flags_and_execution_flags_are_identical_class():
    from engine.schemas.engine import TaskFlags
    from api.models import ExecutionFlags

    assert ExecutionFlags is TaskFlags
    assert issubclass(TaskFlags, BaseModel)


def test_task_flags_canonical_fields_and_defaults():
    from engine.schemas.engine import TaskFlags

    flags = TaskFlags()
    assert flags.check_http is True
    assert flags.recursive_san is False
    assert flags.out_of_scope_depth == 0
    assert flags.check_virtual_hosts is True
    assert flags.timeout == 10
    assert flags.workers == 100
    assert flags.rate == 50.0
    assert flags.user_agent is None


def test_task_flags_no_cli_arg_metadata_pollution():
    from engine.schemas.engine import TaskFlags

    for field_name, field_info in TaskFlags.model_fields.items():
        if field_info.json_schema_extra:
            assert "cli_arg" not in field_info.json_schema_extra, (
                f"Field '{field_name}' contains legacy 'cli_arg' metadata"
            )
            assert "is_switch" not in field_info.json_schema_extra, (
                f"Field '{field_name}' contains legacy 'is_switch' metadata"
            )


def test_task_flags_accepts_legacy_aliases():
    from engine.schemas.engine import TaskFlags

    # Legacy alias keys used in earlier engine versions
    data = {
        "timeout_seconds": 25,
        "recursive_san_check": True,
    }
    flags = TaskFlags.model_validate(data)
    assert flags.timeout == 25
    assert flags.recursive_san is True


def test_task_config_to_dict_serializes_flags():
    from engine.schemas.engine import TaskConfig, TaskFlags

    flags = TaskFlags(timeout=15, recursive_san=True)
    config = TaskConfig(target="1.1.1.1", ports=[80, 443], flags=flags)
    d = config.to_dict()
    assert isinstance(d["flags"], dict)
    assert d["flags"]["timeout"] == 15
    assert d["flags"]["recursive_san"] is True
