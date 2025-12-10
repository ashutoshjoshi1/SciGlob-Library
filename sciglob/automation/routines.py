"""
Routine definition and parsing for SciGlob automation.

Routines are predefined measurement sequences similar to Blick .rout files.
Each routine has a two-letter code (e.g., "DS" for direct sun, "SS" for sun search).

Routine File Format:
    DESCRIPTION -> Brief description of the routine
    SET POINTING -> DELTA=MIDDLE; AZI=0; ZEN=45; AZIMODE=ABS; ZENMODE=ABS
    SET FILTERWHEELS -> FW1=OPEN; FW2=DIFF
    SET SPECTROMETER -> IT=100; NCYCLES=10; NREPETITIONS=5
    MEASURE -> DISPLAY=MEAN; SAVE=STDERR
    CHECK INTENSITY -> ADJUSTIT=FROMCURRENT; %SATURATION=80
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional, Union

from sciglob.automation.exceptions import (
    RoutineError,
    RoutineNotFoundError,
    RoutineParseError,
)

logger = logging.getLogger(__name__)


class RoutineKeyword(Enum):
    """Valid keywords for routine files."""
    DESCRIPTION = auto()
    GETSCRIPT = auto()
    COMMAND = auto()
    DURATION = auto()
    START_LOOP = auto()
    STOP_LOOP = auto()
    SET_POINTING = auto()
    SET_FILTERWHEELS = auto()
    SET_SHADOWBAND = auto()
    SET_SPECTROMETER = auto()
    MEASURE = auto()
    CHECK_INTENSITY = auto()
    PROCESSINFO = auto()

    @classmethod
    def from_string(cls, value: str) -> Optional["RoutineKeyword"]:
        """Convert string to RoutineKeyword."""
        mapping = {
            "DESCRIPTION": cls.DESCRIPTION,
            "GETSCRIPT": cls.GETSCRIPT,
            "COMMAND": cls.COMMAND,
            "DURATION": cls.DURATION,
            "START LOOP": cls.START_LOOP,
            "STOP LOOP": cls.STOP_LOOP,
            "SET POINTING": cls.SET_POINTING,
            "SET FILTERWHEELS": cls.SET_FILTERWHEELS,
            "SET SHADOWBAND": cls.SET_SHADOWBAND,
            "SET SPECTROMETER": cls.SET_SPECTROMETER,
            "MEASURE": cls.MEASURE,
            "CHECK INTENSITY": cls.CHECK_INTENSITY,
            "PROCESSINFO": cls.PROCESSINFO,
        }
        return mapping.get(value.upper().strip())


class PointingMode(Enum):
    """Pointing modes for tracker positioning."""
    ABSOLUTE = "ABS"
    RELATIVE_SUN = "RELSUN"
    RELATIVE_MOON = "RELMOON"
    ANGLE_SUN = "ANGSUN"
    ANGLE_MOON = "ANGMOON"


class ProcessType(Enum):
    """Data processing type indicators."""
    ONLY_L1 = "ONLYL1"
    NO_L1 = "NOL1"
    SUN = "SUN"
    MOON = "MOON"
    SKY = "SKY"
    TARGET = "TARGET"
    PROFILE = "PROFILE"
    ALMUCANTAR = "ALMUCANTAR"
    LAMP = "LAMP"
    SPECIAL = "SPECIAL"


@dataclass
class RoutineParameters:
    """
    Global parameters for routine execution.

    Based on Blick's LoadRoutineParameters() in blick_params.py
    """
    # Estimated durations in seconds
    intensity_check_duration: float = 1.0
    filterwheel_change_duration: float = 1.0
    filterwheel_reset_duration: float = 5.0
    pointing_change_duration: float = 2.0
    tracker_reset_duration: float = 60.0
    shadowband_change_duration: float = 1.0
    shadowband_reset_duration: float = 3.0

    # Separators for routine files
    keyword_separator: str = "->"
    subkeyword_separator: str = ";"
    value_separator: str = "="
    spectrometer_separator: str = "_"

    # Intensity check tolerance [%]
    intensity_check_tolerance: float = 10.0

    # Maximum number of spectrometers
    max_spectrometers: int = 3

    # Valid filters
    functional_filters: list[str] = field(default_factory=lambda: [
        "OPEN", "U340", "BP300", "LPNIR"
    ])

    valid_filters: list[str] = field(default_factory=lambda: [
        "OPAQUE", "OPEN", "U340", "BP300", "LPNIR",
        "DIFF", "U340+DIFF", "BP300+DIFF", "LPNIR+DIFF",
        "ND1", "ND2", "ND3", "ND4", "ND5",
        "DIFF1", "DIFF2", "DIFF3", "DIFF4", "DIFF5",
    ])

    # Routine file extension
    routine_extension: str = ".rout"

    # Schedule file extension
    schedule_extension: str = ".sked"


# Global routine parameters instance
ROUTINE_PARAMS = RoutineParameters()


@dataclass
class RoutineCommand:
    """
    A single command within a routine.

    Attributes:
        keyword: The command keyword (e.g., SET_POINTING)
        subkeywords: Dictionary of subkeyword-value pairs
        raw_line: Original line from routine file
        line_number: Line number in source file
    """
    keyword: RoutineKeyword
    subkeywords: dict[str, Any] = field(default_factory=dict)
    raw_line: str = ""
    line_number: int = 0

    def get(self, key: str, default: Any = None) -> Any:
        """Get a subkeyword value with optional default."""
        return self.subkeywords.get(key.upper(), default)

    def __repr__(self) -> str:
        return f"RoutineCommand({self.keyword.name}, {self.subkeywords})"


@dataclass
class Routine:
    """
    A complete routine definition.

    Routines are identified by a two-letter code and contain
    a sequence of commands to execute.

    Attributes:
        code: Two-letter routine code (e.g., "DS", "SS")
        description: Human-readable description
        commands: List of commands in execution order
        source_file: Path to source routine file
    """
    code: str
    description: str = ""
    commands: list[RoutineCommand] = field(default_factory=list)
    source_file: Optional[Path] = None

    def __post_init__(self):
        """Validate routine code format."""
        if len(self.code) != 2:
            raise RoutineError(
                f"Routine code must be exactly 2 characters, got '{self.code}'",
                routine_code=self.code
            )
        self.code = self.code.upper()

    @classmethod
    def from_file(cls, filepath: Union[str, Path]) -> "Routine":
        """
        Load a routine from a .rout file.

        Args:
            filepath: Path to the routine file

        Returns:
            Routine instance

        Raises:
            RoutineNotFoundError: If file doesn't exist
            RoutineParseError: If file cannot be parsed
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise RoutineNotFoundError(filepath.stem[:2])

        reader = RoutineReader()
        return reader.read_routine(filepath)

    @classmethod
    def from_string(cls, code: str, content: str) -> "Routine":
        """
        Create a routine from string content.

        Args:
            code: Two-letter routine code
            content: Routine file content as string

        Returns:
            Routine instance
        """
        reader = RoutineReader()
        return reader.parse_routine(code, content.splitlines())

    def get_commands_by_keyword(
        self, keyword: RoutineKeyword
    ) -> list[RoutineCommand]:
        """Get all commands matching a keyword."""
        return [cmd for cmd in self.commands if cmd.keyword == keyword]

    def get_duration_estimate(self, params: Optional[RoutineParameters] = None) -> float:
        """
        Estimate total routine duration in seconds.

        This is a rough estimate based on command types.
        """
        params = params or ROUTINE_PARAMS
        total = 0.0

        for cmd in self.commands:
            if cmd.keyword == RoutineKeyword.SET_POINTING:
                total += params.pointing_change_duration
            elif cmd.keyword == RoutineKeyword.SET_FILTERWHEELS:
                total += params.filterwheel_change_duration
            elif cmd.keyword == RoutineKeyword.SET_SHADOWBAND:
                total += params.shadowband_change_duration
            elif cmd.keyword == RoutineKeyword.CHECK_INTENSITY:
                total += params.intensity_check_duration
            elif cmd.keyword == RoutineKeyword.MEASURE:
                # Estimate from spectrometer settings if available
                total += 1.0  # Default 1 second
            elif cmd.keyword == RoutineKeyword.DURATION:
                length = cmd.get("LENGTH")
                if isinstance(length, (int, float)):
                    total += length

        return total

    def validate(self, system_status: Optional[dict[str, Any]] = None) -> list[str]:
        """
        Validate the routine against system requirements.

        Args:
            system_status: Optional dict with connected hardware info

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check for basic structure
        if not self.commands:
            errors.append("Routine has no commands")

        # Check loop balance
        loop_depth = 0
        for cmd in self.commands:
            if cmd.keyword == RoutineKeyword.START_LOOP:
                loop_depth += 1
            elif cmd.keyword == RoutineKeyword.STOP_LOOP:
                loop_depth -= 1
                if loop_depth < 0:
                    errors.append(f"STOP LOOP without matching START LOOP at line {cmd.line_number}")

        if loop_depth > 0:
            errors.append(f"Unclosed loop(s): {loop_depth} START LOOP without STOP LOOP")

        # System requirements check
        if system_status:
            for cmd in self.commands:
                if cmd.keyword == RoutineKeyword.SET_POINTING:
                    if not system_status.get("tracker_connected"):
                        errors.append("Routine requires tracker but tracker not connected")
                elif cmd.keyword == RoutineKeyword.SET_FILTERWHEELS:
                    if not system_status.get("head_sensor_connected"):
                        errors.append("Routine requires head sensor but head sensor not connected")
                elif cmd.keyword in (RoutineKeyword.SET_SPECTROMETER, RoutineKeyword.MEASURE):
                    if not system_status.get("spectrometer_connected"):
                        errors.append("Routine requires spectrometer but spectrometer not connected")

        return errors

    def __repr__(self) -> str:
        return f"Routine('{self.code}', commands={len(self.commands)})"


class RoutineReader:
    """
    Parser for routine files.

    Handles the Blick-style routine file format with keywords,
    subkeywords, and values.
    """

    def __init__(self, params: Optional[RoutineParameters] = None):
        """Initialize with optional custom parameters."""
        self.params = params or ROUTINE_PARAMS
        self._subkeyword_defaults = self._build_subkeyword_defaults()

    def _build_subkeyword_defaults(self) -> dict[str, dict[str, Any]]:
        """Build default values for subkeywords."""
        return {
            "SET_POINTING": {
                "DELTA": "MIDDLE",
                "AZI": "CURRENT",
                "ZEN": "CURRENT",
                "AZIMODE": "ABS",
                "ZENMODE": "ABS",
            },
            "SET_FILTERWHEELS": {
                "FUNCFILT": "XXX",
                "FW1": "CURRENT",
                "FW2": "CURRENT",
            },
            "SET_SHADOWBAND": {
                "SBZEN": "CURRENT",
                "SBZENMODE": "ABS",
            },
            "SET_SPECTROMETER": {
                "IT": "CURRENT",
                "NCYCLES": "AUTO",
                "NREPETITIONS": "AUTO",
                "DURATION": "AUTO",
                "DARKRATIO": 0,
            },
            "MEASURE": {
                "DISPLAY": "MEAN",
                "SAVE": "NO",
                "SATCHECK": "YES",
            },
            "CHECK_INTENSITY": {
                "ADJUSTIT": "FROMCURRENT",
                "ADJUSTND": "NO",
                "%SATURATION": 80,
                "DARKESTIMATION": "THEORY",
                "ITLIMIT": "ITMAX",
            },
            "DURATION": {
                "LENGTH": 0,
                "TIMEMODE": "ADDED",
            },
            "PROCESSINFO": {
                "TYPE": "ONLYL1",
                "DISTANCE": "NO",
            },
        }

    def read_all_routines(self, directory: Union[str, Path]) -> list[Routine]:
        """
        Read all routine files from a directory.

        Args:
            directory: Path to routines directory

        Returns:
            List of parsed Routine objects
        """
        directory = Path(directory)
        if not directory.is_dir():
            raise RoutineError(f"Invalid routine directory: {directory}")

        routines = []
        for filepath in sorted(directory.glob(f"*{self.params.routine_extension}")):
            try:
                routine = self.read_routine(filepath)
                routines.append(routine)
            except RoutineParseError as e:
                logger.warning(f"Failed to parse routine {filepath}: {e}")

        return routines

    def read_routine(self, filepath: Union[str, Path]) -> Routine:
        """
        Read a single routine file.

        Args:
            filepath: Path to the routine file

        Returns:
            Parsed Routine object
        """
        filepath = Path(filepath)
        code = filepath.stem[:2].upper()

        if len(filepath.stem) != 2:
            raise RoutineParseError(
                f"Invalid routine filename '{filepath.name}'. "
                "Routine filename must be exactly 2 letters.",
                routine_code=code
            )

        try:
            with open(filepath, encoding='utf-8') as f:
                lines = f.readlines()
        except OSError as e:
            raise RoutineParseError(
                f"Cannot read routine file: {e}",
                routine_code=code
            ) from e

        routine = self.parse_routine(code, lines)
        routine.source_file = filepath
        return routine

    def parse_routine(self, code: str, lines: list[str]) -> Routine:
        """
        Parse routine content from lines.

        Args:
            code: Two-letter routine code
            lines: Lines from routine file

        Returns:
            Parsed Routine object
        """
        commands: list[RoutineCommand] = []
        description = "No description given"
        has_description = False

        for line_num, line in enumerate(lines, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            try:
                cmd = self._parse_line(line, line_num)
                if cmd:
                    if cmd.keyword == RoutineKeyword.DESCRIPTION:
                        if not has_description:
                            description = cmd.get("VALUE", "")
                            has_description = True
                        else:
                            # Append to existing description
                            description += "\n" + cmd.get("VALUE", "")
                    else:
                        commands.append(cmd)
            except Exception as e:
                raise RoutineParseError(
                    str(e),
                    routine_code=code,
                    line_number=line_num,
                    line_content=line
                ) from e

        return Routine(
            code=code,
            description=description,
            commands=commands
        )

    def _parse_line(self, line: str, line_num: int) -> Optional[RoutineCommand]:
        """Parse a single line from a routine file."""
        sep = self.params.keyword_separator

        # Split on keyword separator
        parts = line.split(sep, 1)
        keyword_str = parts[0].strip()

        # Get keyword enum
        keyword = RoutineKeyword.from_string(keyword_str)
        if keyword is None:
            if sep in line:
                raise RoutineParseError(f"Unknown keyword '{keyword_str}'")
            # Line without separator that's not a keyword - skip
            return None

        # Parse subkeywords if present
        subkeywords = {}
        if len(parts) > 1:
            value_str = parts[1].strip()

            # Special handling for DESCRIPTION and COMMAND
            if keyword in (RoutineKeyword.DESCRIPTION, RoutineKeyword.COMMAND):
                subkeywords["VALUE"] = value_str
            elif keyword == RoutineKeyword.GETSCRIPT:
                subkeywords["SCRIPT"] = value_str
            elif keyword == RoutineKeyword.STOP_LOOP:
                pass  # No subkeywords
            else:
                subkeywords = self._parse_subkeywords(keyword, value_str)

        # Apply defaults
        keyword_name = keyword.name.replace("_", " ")
        keyword_key = keyword_name.replace(" ", "_")
        defaults = self._subkeyword_defaults.get(keyword_key, {})
        for key, default_value in defaults.items():
            if key not in subkeywords:
                subkeywords[key] = default_value

        return RoutineCommand(
            keyword=keyword,
            subkeywords=subkeywords,
            raw_line=line,
            line_number=line_num
        )

    def _parse_subkeywords(
        self, keyword: RoutineKeyword, value_str: str
    ) -> dict[str, Any]:
        """Parse subkeyword-value pairs from a string."""
        subkeywords = {}

        # Split on subkeyword separator
        pairs = value_str.split(self.params.subkeyword_separator)

        for pair in pairs:
            pair = pair.strip()
            if not pair:
                continue

            # Split on value separator
            if self.params.value_separator not in pair:
                raise RoutineParseError(
                    f"Missing '{self.params.value_separator}' in '{pair}'"
                )

            key, value = pair.split(self.params.value_separator, 1)
            key = key.strip().upper()
            value = value.strip()

            # Convert value to appropriate type
            subkeywords[key] = self._convert_value(value)

        return subkeywords

    def _convert_value(self, value: str) -> Any:
        """Convert a string value to appropriate Python type."""
        # Check for boolean-like values
        if value.upper() in ("YES", "TRUE", "ON"):
            return True
        if value.upper() in ("NO", "FALSE", "OFF"):
            return False

        # Check for integer
        try:
            return int(value)
        except ValueError:
            pass

        # Check for float
        try:
            return float(value)
        except ValueError:
            pass

        # Check for list (comma-separated values)
        if ',' in value:
            parts = [self._convert_value(p.strip()) for p in value.split(',')]
            return parts

        # Keep as string
        return value

    def _check_xij_value(self, value: str) -> tuple[bool, Any]:
        """
        Check if value is XIJ-style (loop variable).

        XIJ values are used for loop iteration, e.g., "XIJ" or "XIJ(3)".

        Returns:
            (is_xij, xij_index) tuple
        """
        if not isinstance(value, str):
            return False, None

        if not value.startswith("XIJ"):
            return False, None

        remainder = value[3:]
        if not remainder:
            return True, 0

        # Check for XIJ(n) format
        match = re.match(r'\((\d+)\)', remainder)
        if match:
            return True, int(match.group(1)) - 1

        return False, None


def decompose_routine_string(
    routine_string: str,
    routines: Optional[list[Routine]] = None,
    repeatable: bool = True,
) -> list[tuple[str, list[int]]]:
    """
    Decompose a routine sequence string into individual routines.

    Routine strings can be:
    - Single routine: "DS"
    - Sequence: "DSSS"
    - With repetitions: "DS3"
    - Combined: "DS3SS2FR"

    Args:
        routine_string: String of routine codes with optional repetition counts
        routines: Optional list of valid routines for validation
        repeatable: Whether routines can be repeated

    Returns:
        List of (routine_code, time_indices) tuples
    """
    routine_string = routine_string.upper().strip()
    result = []

    i = 0
    while i < len(routine_string):
        if i + 1 >= len(routine_string):
            raise RoutineParseError(f"Incomplete routine code at position {i}")

        # Extract two-letter code
        code = routine_string[i:i+2]
        i += 2

        # Validate if routines list provided
        if routines:
            valid_codes = [r.code for r in routines]
            if code not in valid_codes:
                raise RoutineNotFoundError(code)

        # Check for repetition count
        repetitions = 1
        rep_str = ""
        while i < len(routine_string) and routine_string[i].isdigit():
            rep_str += routine_string[i]
            i += 1

        if rep_str:
            repetitions = int(rep_str)
            if not repeatable and repetitions > 1:
                raise RoutineParseError(
                    f"Repetitions not allowed for routine '{code}'"
                )

        # Add to result (with time indices placeholder)
        for _ in range(repetitions):
            result.append((code, [0, 0, 0]))

    return result

