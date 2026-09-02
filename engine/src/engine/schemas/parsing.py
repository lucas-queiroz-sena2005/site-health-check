import dataclasses

@dataclasses.dataclass
class TargetSegment:
    segment_type: str      # "domain", "ip", or "cidr"
    data: str             # e.g., 'example.com', '192.168.1.1', '10.0.0.5-10.0.0.8'
    suffix: str | None    # e.g., '/24' or None

@dataclasses.dataclass
class TargetValidationResult:
    is_valid: bool
    error_message: str
    segments: list[TargetSegment]
