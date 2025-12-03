"""Custom exceptions for SciGlob automation module."""

from typing import Optional, List
from sciglob.core.exceptions import SciGlobError


class AutomationError(SciGlobError):
    """Base exception for all automation errors."""
    pass


class RoutineError(AutomationError):
    """Raised when a routine operation fails."""
    
    def __init__(self, message: str, routine_code: Optional[str] = None):
        super().__init__(message)
        self.routine_code = routine_code


class ScheduleError(AutomationError):
    """Raised when a schedule operation fails."""
    
    def __init__(self, message: str, schedule_name: Optional[str] = None):
        super().__init__(message)
        self.schedule_name = schedule_name


class ExecutionError(AutomationError):
    """Raised when routine/schedule execution fails."""
    
    def __init__(
        self,
        message: str,
        command: Optional[str] = None,
        recovery_level: int = 0,
    ):
        super().__init__(message)
        self.command = command
        self.recovery_level = recovery_level


class TimingError(AutomationError):
    """Raised when time calculation or scheduling fails."""
    
    def __init__(self, message: str, time_reference: Optional[str] = None):
        super().__init__(message)
        self.time_reference = time_reference


class RoutineNotFoundError(RoutineError):
    """Raised when a routine file or code is not found."""
    
    def __init__(self, routine_code: str, search_paths: Optional[List[str]] = None):
        message = f"Routine '{routine_code}' not found"
        if search_paths:
            message += f" in paths: {', '.join(search_paths)}"
        super().__init__(message, routine_code)
        self.search_paths = search_paths


class ScheduleParseError(ScheduleError):
    """Raised when a schedule file cannot be parsed."""
    
    def __init__(
        self,
        message: str,
        schedule_name: Optional[str] = None,
        line_number: Optional[int] = None,
        line_content: Optional[str] = None,
    ):
        full_message = message
        if line_number is not None:
            full_message = f"Line {line_number}: {message}"
        if line_content:
            full_message += f"\n  Content: '{line_content}'"
        super().__init__(full_message, schedule_name)
        self.line_number = line_number
        self.line_content = line_content


class RoutineParseError(RoutineError):
    """Raised when a routine file cannot be parsed."""
    
    def __init__(
        self,
        message: str,
        routine_code: Optional[str] = None,
        line_number: Optional[int] = None,
        line_content: Optional[str] = None,
    ):
        full_message = message
        if line_number is not None:
            full_message = f"Line {line_number}: {message}"
        if line_content:
            full_message += f"\n  Content: '{line_content}'"
        super().__init__(full_message, routine_code)
        self.line_number = line_number
        self.line_content = line_content


class SystemRequirementError(RoutineError):
    """Raised when system requirements for a routine are not met."""
    
    def __init__(
        self,
        message: str,
        routine_code: Optional[str] = None,
        missing_requirements: Optional[List[str]] = None,
    ):
        super().__init__(message, routine_code)
        self.missing_requirements = missing_requirements or []


class LoopError(RoutineError):
    """Raised when there's an error in a loop construct."""
    
    def __init__(
        self,
        message: str,
        routine_code: Optional[str] = None,
        loop_index: Optional[int] = None,
    ):
        super().__init__(message, routine_code)
        self.loop_index = loop_index


class IntensityCheckError(ExecutionError):
    """Raised when intensity check fails during routine execution."""
    
    def __init__(
        self,
        message: str,
        saturation_level: Optional[float] = None,
        expected_level: Optional[float] = None,
    ):
        super().__init__(message)
        self.saturation_level = saturation_level
        self.expected_level = expected_level


class SaturationError(ExecutionError):
    """Raised when detector saturation is detected."""
    
    def __init__(
        self,
        message: str,
        saturation_count: int = 0,
        max_allowed: int = 0,
    ):
        super().__init__(message)
        self.saturation_count = saturation_count
        self.max_allowed = max_allowed

