"""
Schedule definition and parsing for SciGlob automation.

Schedules define time-based execution of routine sequences,
similar to Blick .sked files.

Schedule File Format:
    # Comments start with #
    {
        'label' -> 'morning_sunsearch',
        'start' -> 'solarzen90am',
        'end' -> 'localnoon',
        'repetitions' -> 3,
        'priority' -> 10,
        'commands' -> 'SSDS5'
    }
    {
        'label' -> 'afternoon_measurements',
        'start' -> 'localnoon+00:30',
        'commands' -> 'DS10SS',
        'priority' -> 5
    }

Time References:
    - localmidnight: Local midnight
    - localnoon: Local solar noon
    - solarzen90am: Solar zenith 90° (sunrise)
    - solarzen90pm: Solar zenith 90° (sunset)
    - sunrise+HH:MM: Time offset from sunrise
    - sunset-HH:MM: Time offset from sunset
    - HH:MM:SS: Absolute UTC time
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple
import logging
import re

from sciglob.automation.exceptions import (
    ScheduleError,
    ScheduleParseError,
    RoutineNotFoundError,
)
from sciglob.automation.routines import (
    Routine,
    RoutineReader,
    RoutineParameters,
    ROUTINE_PARAMS,
    decompose_routine_string,
)

logger = logging.getLogger(__name__)


class TimeReference(Enum):
    """Types of time references for schedule start/end times."""
    ABSOLUTE = auto()          # HH:MM:SS UTC
    LOCAL_MIDNIGHT = auto()    # localmidnight
    LOCAL_NOON = auto()        # localnoon
    SOLAR_ZEN_90_AM = auto()   # solarzen90am (sunrise)
    SOLAR_ZEN_90_PM = auto()   # solarzen90pm (sunset)
    SUNRISE = auto()           # sunrise
    SUNSET = auto()            # sunset
    MOON_RISE = auto()         # moonrise
    MOON_SET = auto()          # moonset
    THEN = auto()              # After previous sequence
    UNDEFINED = auto()         # End time not defined


class ScheduleCondition(Enum):
    """Conditional execution criteria for schedule entries."""
    NONE = auto()
    MOON_VISIBLE = auto()
    SUN_VISIBLE = auto()
    MONTH_DAY = auto()
    MOON_PHASE = auto()


@dataclass
class ScheduleParameters:
    """
    Parameters for schedule execution.
    
    Based on Blick's schedule handling in blick_osparams.py
    """
    # Time gap in schedule that triggers tracker parking [seconds]
    parking_gap: float = 20 * 60  # 20 minutes
    
    # Maximum time tolerance to start routine after requested start [seconds]
    start_time_tolerance: float = 120  # 2 minutes
    
    # Time tolerance to decide if next day's schedule is used [seconds]
    next_day_tolerance: float = 60  # 1 minute
    
    # Default priority level
    default_priority: int = 5
    
    # Schedule file extension
    schedule_extension: str = ".sked"
    
    # Keyword separator in schedule files
    keyword_separator: str = "->"
    
    # Allowed schedule entry keywords
    allowed_keywords: List[str] = field(default_factory=lambda: [
        "label", "start", "end", "refrout", "reftime", "repetitions",
        "priority", "startwith", "commands", "if"
    ])
    
    # Required keywords for a valid entry
    required_keywords: List[str] = field(default_factory=lambda: [
        "label", "start", "priority", "commands"
    ])


# Global schedule parameters instance
SCHEDULE_PARAMS = ScheduleParameters()


@dataclass
class ScheduleEntry:
    """
    A single entry in a schedule defining when to run routines.
    
    Attributes:
        label: Unique identifier for this entry
        start_time_ref: Time reference for start
        start_offset: Offset from time reference (can be negative)
        end_time_ref: Time reference for end (optional)
        end_offset: Offset from end time reference
        repetitions: Number of times to repeat (-1 for unlimited until end)
        priority: Execution priority (higher = more important)
        commands: Routine sequence string (e.g., "DS5SS")
        condition: Optional execution condition
        condition_value: Value for condition (e.g., day number for MONTH_DAY)
        start_with: Routine to execute before main commands (non-repeating)
        reference_routine: Routine used for time calculations
        reference_time: "b" (beginning), "m" (middle), or "e" (end) of reference routine
    """
    label: str
    start_time_ref: TimeReference
    start_offset: timedelta = field(default_factory=timedelta)
    end_time_ref: TimeReference = TimeReference.UNDEFINED
    end_offset: timedelta = field(default_factory=timedelta)
    repetitions: int = 1
    priority: int = 5
    commands: str = ""
    condition: ScheduleCondition = ScheduleCondition.NONE
    condition_value: Optional[Any] = None
    start_with: str = ""
    reference_routine: str = ""
    reference_time: str = "b"  # b=beginning, m=middle, e=end
    
    # Computed times (set during schedule processing)
    computed_start: Optional[datetime] = None
    computed_end: Optional[datetime] = None
    
    # Parsed routine info
    routine_params: List[Tuple[str, List[int]]] = field(default_factory=list)
    start_with_params: List[Tuple[str, List[int]]] = field(default_factory=list)
    
    # Source tracking
    raw_content: str = ""
    source_index: int = 0
    
    def __post_init__(self):
        """Initialize reference routine from commands if not set."""
        if not self.reference_routine and self.start_with:
            self.reference_routine = self.start_with[:2]
        elif not self.reference_routine and self.commands:
            self.reference_routine = self.commands[:2]
    
    def get_all_routine_codes(self) -> List[str]:
        """Get all routine codes used in this entry."""
        codes = []
        if self.start_with:
            codes.extend([r[0] for r in self.start_with_params])
        codes.extend([r[0] for r in self.routine_params])
        return codes
    
    def check_condition(
        self,
        current_time: datetime,
        location: Optional[Dict[str, float]] = None,
    ) -> bool:
        """
        Check if the condition for this entry is satisfied.
        
        Args:
            current_time: Current datetime for evaluation
            location: Location dict with 'latitude', 'longitude'
            
        Returns:
            True if condition is satisfied or no condition set
        """
        if self.condition == ScheduleCondition.NONE:
            return True
        
        if self.condition == ScheduleCondition.MONTH_DAY:
            if self.condition_value is not None:
                return current_time.day == self.condition_value
            return True
        
        if self.condition == ScheduleCondition.MOON_VISIBLE:
            # Would need astronomical calculations
            # For now, return True (needs implementation with timing module)
            return True
        
        if self.condition == ScheduleCondition.SUN_VISIBLE:
            # Would need astronomical calculations
            return True
        
        if self.condition == ScheduleCondition.MOON_PHASE:
            # Would need lunar phase calculation
            return True
        
        return True
    
    def __repr__(self) -> str:
        return f"ScheduleEntry('{self.label}', start={self.start_time_ref.name}, commands='{self.commands}')"


@dataclass
class Schedule:
    """
    A complete schedule containing multiple entries.
    
    Attributes:
        name: Schedule name (usually filename without extension)
        entries: List of schedule entries in order
        source_file: Path to source schedule file
    """
    name: str
    entries: List[ScheduleEntry] = field(default_factory=list)
    source_file: Optional[Path] = None
    
    @classmethod
    def from_file(
        cls,
        filepath: Union[str, Path],
        routines: Optional[List[Routine]] = None,
    ) -> "Schedule":
        """
        Load a schedule from a .sked file.
        
        Args:
            filepath: Path to the schedule file
            routines: Optional list of valid routines for validation
            
        Returns:
            Schedule instance
            
        Raises:
            ScheduleParseError: If file cannot be parsed
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise ScheduleParseError(
                f"Schedule file not found: {filepath}",
                schedule_name=filepath.stem
            )
        
        reader = ScheduleReader()
        return reader.read_schedule(filepath, routines)
    
    @classmethod
    def from_string(
        cls,
        name: str,
        content: str,
        routines: Optional[List[Routine]] = None,
    ) -> "Schedule":
        """
        Create a schedule from string content.
        
        Args:
            name: Schedule name
            content: Schedule file content as string
            routines: Optional list of valid routines for validation
            
        Returns:
            Schedule instance
        """
        reader = ScheduleReader()
        return reader.parse_schedule(name, content.splitlines(), routines)
    
    def get_entry_by_label(self, label: str) -> Optional[ScheduleEntry]:
        """Get schedule entry by label."""
        for entry in self.entries:
            if entry.label == label:
                return entry
        return None
    
    def get_entries_by_priority(self, min_priority: int = 0) -> List[ScheduleEntry]:
        """Get entries sorted by priority (highest first)."""
        filtered = [e for e in self.entries if e.priority >= min_priority]
        return sorted(filtered, key=lambda e: -e.priority)
    
    def get_all_routine_codes(self) -> List[str]:
        """Get unique list of all routine codes used in schedule."""
        codes = set()
        for entry in self.entries:
            codes.update(entry.get_all_routine_codes())
        return sorted(codes)
    
    def validate(self, routines: Optional[List[Routine]] = None) -> List[str]:
        """
        Validate the schedule.
        
        Args:
            routines: Optional list of valid routines
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Check for duplicate labels
        labels = [e.label for e in self.entries]
        seen = set()
        for label in labels:
            if label in seen:
                errors.append(f"Duplicate label: '{label}'")
            seen.add(label)
        
        # Check first entry doesn't use THEN
        if self.entries and self.entries[0].start_time_ref == TimeReference.THEN:
            errors.append("First entry cannot use 'THEN' as start time")
        
        # Check routine codes exist
        if routines:
            valid_codes = {r.code for r in routines}
            for entry in self.entries:
                for code in entry.get_all_routine_codes():
                    if code not in valid_codes:
                        errors.append(f"Unknown routine '{code}' in entry '{entry.label}'")
        
        # Check repetitions vs end time
        for entry in self.entries:
            if entry.end_time_ref == TimeReference.UNDEFINED and entry.repetitions == -1:
                errors.append(
                    f"Entry '{entry.label}': Cannot have unlimited repetitions "
                    "without end time"
                )
        
        return errors
    
    def __repr__(self) -> str:
        return f"Schedule('{self.name}', entries={len(self.entries)})"


class ScheduleReader:
    """
    Parser for schedule files.
    
    Handles the Blick-style schedule file format with curly brace
    delimited entries containing key-value pairs.
    """
    
    def __init__(self, params: Optional[ScheduleParameters] = None):
        """Initialize with optional custom parameters."""
        self.params = params or SCHEDULE_PARAMS
    
    def read_schedule(
        self,
        filepath: Union[str, Path],
        routines: Optional[List[Routine]] = None,
    ) -> Schedule:
        """
        Read a schedule from a file.
        
        Args:
            filepath: Path to the schedule file
            routines: Optional list of valid routines for validation
            
        Returns:
            Parsed Schedule object
        """
        filepath = Path(filepath)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except IOError as e:
            raise ScheduleParseError(
                f"Cannot read schedule file: {e}",
                schedule_name=filepath.stem
            )
        
        schedule = self.parse_schedule(filepath.stem, lines, routines)
        schedule.source_file = filepath
        return schedule
    
    def parse_schedule(
        self,
        name: str,
        lines: List[str],
        routines: Optional[List[Routine]] = None,
    ) -> Schedule:
        """
        Parse schedule content from lines.
        
        Args:
            name: Schedule name
            lines: Lines from schedule file
            routines: Optional list of valid routines for validation
            
        Returns:
            Parsed Schedule object
        """
        # Remove comments and empty lines
        clean_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                clean_lines.append(line)
        
        # Find bracket pairs
        content = ''.join(clean_lines)
        entries = self._extract_entries(content, name)
        
        # Parse each entry
        parsed_entries = []
        labels_seen = set()
        
        for idx, entry_content in enumerate(entries):
            try:
                entry = self._parse_entry(entry_content, idx, routines)
                
                # Check for duplicate labels
                if entry.label in labels_seen:
                    raise ScheduleParseError(
                        f"Duplicate label '{entry.label}'",
                        schedule_name=name
                    )
                labels_seen.add(entry.label)
                
                parsed_entries.append(entry)
            except ScheduleParseError:
                raise
            except Exception as e:
                raise ScheduleParseError(
                    f"Error parsing entry {idx + 1}: {e}",
                    schedule_name=name
                )
        
        # Validate first entry doesn't use THEN
        if parsed_entries and parsed_entries[0].start_time_ref == TimeReference.THEN:
            raise ScheduleParseError(
                "First entry cannot use 'THEN' as start time",
                schedule_name=name
            )
        
        return Schedule(name=name, entries=parsed_entries)
    
    def _extract_entries(self, content: str, schedule_name: str) -> List[str]:
        """Extract individual entry contents from schedule content."""
        entries = []
        depth = 0
        start = -1
        
        for i, char in enumerate(content):
            if char == '{':
                if depth == 0:
                    start = i + 1
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    entries.append(content[start:i].strip())
                    start = -1
                elif depth < 0:
                    raise ScheduleParseError(
                        "Unmatched closing bracket '}'",
                        schedule_name=schedule_name
                    )
        
        if depth > 0:
            raise ScheduleParseError(
                f"Unclosed bracket(s): {depth} opening '{{' without closing '}}'",
                schedule_name=schedule_name
            )
        
        return entries
    
    def _parse_entry(
        self,
        content: str,
        index: int,
        routines: Optional[List[Routine]] = None,
    ) -> ScheduleEntry:
        """Parse a single schedule entry."""
        # Remove quotes and clean up content
        content = content.replace("'", "").replace('"', "")
        
        # Split into key-value pairs
        pairs = content.split(',')
        entry_dict: Dict[str, str] = {}
        
        for pair in pairs:
            pair = pair.strip()
            if not pair:
                continue
            
            if self.params.keyword_separator not in pair:
                raise ScheduleParseError(
                    f"Missing '{self.params.keyword_separator}' in '{pair}'"
                )
            
            key, value = pair.split(self.params.keyword_separator, 1)
            key = key.strip().lower()
            value = value.strip()
            
            # Validate keyword
            if key not in self.params.allowed_keywords:
                raise ScheduleParseError(
                    f"Unknown keyword '{key}'. Allowed: {', '.join(self.params.allowed_keywords)}"
                )
            
            entry_dict[key] = value
        
        # Check required keywords
        for req_key in self.params.required_keywords:
            if req_key not in entry_dict:
                raise ScheduleParseError(f"Missing required keyword '{req_key}'")
        
        # Build ScheduleEntry
        entry = self._build_entry(entry_dict, index, routines)
        entry.raw_content = content
        entry.source_index = index
        
        return entry
    
    def _build_entry(
        self,
        entry_dict: Dict[str, str],
        index: int,
        routines: Optional[List[Routine]] = None,
    ) -> ScheduleEntry:
        """Build a ScheduleEntry from parsed dictionary."""
        # Parse start time
        start_ref, start_offset = self._parse_time_reference(entry_dict["start"])
        
        # Parse end time if present
        end_ref = TimeReference.UNDEFINED
        end_offset = timedelta()
        if "end" in entry_dict and entry_dict["end"].lower() != "undefined":
            end_ref, end_offset = self._parse_time_reference(entry_dict["end"])
        
        # Parse repetitions
        repetitions = 1
        if "repetitions" in entry_dict:
            try:
                repetitions = int(entry_dict["repetitions"])
            except ValueError:
                raise ScheduleParseError(f"Invalid repetitions value: {entry_dict['repetitions']}")
        elif end_ref != TimeReference.UNDEFINED:
            repetitions = -1  # Unlimited until end time
        
        # Parse priority
        priority = self.params.default_priority
        if "priority" in entry_dict:
            try:
                priority = int(entry_dict["priority"])
            except ValueError:
                raise ScheduleParseError(f"Invalid priority value: {entry_dict['priority']}")
        
        # Parse condition
        condition = ScheduleCondition.NONE
        condition_value = None
        if "if" in entry_dict and entry_dict["if"]:
            condition, condition_value = self._parse_condition(entry_dict["if"])
        
        # Parse reference time
        ref_time = "b"
        if "reftime" in entry_dict:
            ref_time = entry_dict["reftime"].lower()
            if ref_time not in ("b", "m", "e"):
                raise ScheduleParseError(f"Invalid reftime '{ref_time}'. Must be 'b', 'm', or 'e'")
        
        # Parse commands
        commands = entry_dict["commands"].upper()
        routine_params = decompose_routine_string(commands, routines)
        
        # Parse start_with if present
        start_with = ""
        start_with_params: List[Tuple[str, List[int]]] = []
        if "startwith" in entry_dict:
            start_with = entry_dict["startwith"].upper()
            start_with_params = decompose_routine_string(start_with, routines, repeatable=False)
        
        # Parse reference routine
        ref_routine = ""
        if "refrout" in entry_dict:
            ref_routine = entry_dict["refrout"].upper()
        elif start_with:
            ref_routine = start_with[:2]
        else:
            ref_routine = commands[:2]
        
        return ScheduleEntry(
            label=entry_dict["label"],
            start_time_ref=start_ref,
            start_offset=start_offset,
            end_time_ref=end_ref,
            end_offset=end_offset,
            repetitions=repetitions,
            priority=priority,
            commands=commands,
            condition=condition,
            condition_value=condition_value,
            start_with=start_with,
            reference_routine=ref_routine,
            reference_time=ref_time,
            routine_params=routine_params,
            start_with_params=start_with_params,
        )
    
    def _parse_time_reference(self, time_str: str) -> Tuple[TimeReference, timedelta]:
        """Parse a time reference string into enum and offset."""
        time_str = time_str.lower().strip()
        offset = timedelta()
        
        # Check for offset (+ or -)
        offset_match = re.search(r'([+-])(\d{2}):(\d{2})', time_str)
        if offset_match:
            sign = 1 if offset_match.group(1) == '+' else -1
            hours = int(offset_match.group(2))
            minutes = int(offset_match.group(3))
            offset = timedelta(hours=hours * sign, minutes=minutes * sign)
            time_str = time_str[:offset_match.start()].strip()
        
        # Map string to TimeReference
        ref_map = {
            "localmidnight": TimeReference.LOCAL_MIDNIGHT,
            "localnoon": TimeReference.LOCAL_NOON,
            "solarzen90am": TimeReference.SOLAR_ZEN_90_AM,
            "solarzen90pm": TimeReference.SOLAR_ZEN_90_PM,
            "sunrise": TimeReference.SUNRISE,
            "sunset": TimeReference.SUNSET,
            "moonrise": TimeReference.MOON_RISE,
            "moonset": TimeReference.MOON_SET,
            "then": TimeReference.THEN,
            "undefined": TimeReference.UNDEFINED,
        }
        
        if time_str in ref_map:
            return ref_map[time_str], offset
        
        # Check for absolute time (HH:MM:SS or HH:MM)
        abs_match = re.match(r'(\d{2}):(\d{2})(?::(\d{2}))?$', time_str)
        if abs_match:
            hours = int(abs_match.group(1))
            minutes = int(abs_match.group(2))
            seconds = int(abs_match.group(3)) if abs_match.group(3) else 0
            offset = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            return TimeReference.ABSOLUTE, offset
        
        raise ScheduleParseError(f"Cannot parse time reference: '{time_str}'")
    
    def _parse_condition(self, condition_str: str) -> Tuple[ScheduleCondition, Optional[Any]]:
        """Parse a condition string."""
        condition_str = condition_str.lower().strip()
        
        if condition_str == "moon_visible":
            return ScheduleCondition.MOON_VISIBLE, None
        
        if condition_str == "sun_visible":
            return ScheduleCondition.SUN_VISIBLE, None
        
        if condition_str.startswith("monthday_"):
            try:
                day = int(condition_str.split("_")[1])
                return ScheduleCondition.MONTH_DAY, day
            except (IndexError, ValueError):
                raise ScheduleParseError(f"Invalid monthday condition: {condition_str}")
        
        if condition_str.startswith("moonphase_"):
            try:
                phase = condition_str.split("_")[1]
                return ScheduleCondition.MOON_PHASE, phase
            except IndexError:
                raise ScheduleParseError(f"Invalid moonphase condition: {condition_str}")
        
        raise ScheduleParseError(f"Unknown condition: {condition_str}")

