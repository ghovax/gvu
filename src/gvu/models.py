"""The run-specific inputs to a shared GaussView workflow."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Result(Enum):
    SUMMARY = "Summary..."
    CHARGES = "Charge Distribution..."
    PCM_CAVITY = "PCM Solvation Cavity..."
    ATOM_PROPERTIES = "Atom Properties..."
    BOND_PROPERTIES = "Bond Properties..."
    SURFACES = "Surfaces/Contours..."
    VIBRATIONS = "Vibrations..."
    NMR = "NMR..."
    EXCITATIONS = "UV-Vis..."
    ORD = "ORD..."
    VIBRONIC = "Vibronic..."
    GROUP_TABLE = "Molecule Group Table..."
    SCAN = "Scan..."
    IRC = "IRC/Path..."
    TRAJECTORY = "Trajectory..."
    OPTIMIZATION = "Optimization..."
    ENERGY = "Energy Plot..."

    @property
    def titles(self):
        return {
            Result.SUMMARY: ("Summary",),
            Result.CHARGES: ("Charge Distribution",),
            Result.PCM_CAVITY: ("PCM Solvation Cavity", "Solvation Cavity"),
            Result.ATOM_PROPERTIES: ("Atom Properties",),
            Result.BOND_PROPERTIES: ("Bond Properties",),
            Result.SURFACES: ("Surfaces and Contours",),
            Result.VIBRATIONS: ("Display Vibrations", "Vibrations"),
            Result.NMR: ("NMR Spectra", "NMR Spectrum"),
            Result.EXCITATIONS: (
                "UV-Vis",
                "UV/Visible",
                "Electronic Spectrum",
                "Electronic Spectra",
            ),
            Result.ORD: ("ORD", "Optical Rotation"),
            Result.VIBRONIC: ("Vibronic",),
            Result.GROUP_TABLE: ("Molecule Group Table",),
            Result.SCAN: ("Scan",),
            Result.IRC: ("IRC Plot",),
            Result.TRAJECTORY: ("Trajectory",),
            Result.OPTIMIZATION: ("Optimization Plot",),
            Result.ENERGY: ("Energy Plot",),
        }[self]

    @property
    def markers(self):
        # These are preflight hints; the live menu's enabled state is authoritative.
        return {
            Result.OPTIMIZATION: ("Optimization completed",),
            Result.EXCITATIONS: ("Excited State",),
            Result.VIBRATIONS: ("Frequencies --",),
            Result.NMR: ("Magnetic shielding", "Isotropic =", "NMR shielding"),
            Result.ORD: ("Optical Rotation", "Optical rotation", "[Alpha]"),
            Result.VIBRONIC: ("Duschinsky", "Vibronic"),
            Result.SCAN: (
                "Summary of the potential surface scan",
                "Summary of Optimized Potential Surface Scan",
            ),
            Result.IRC: ("IRC-IRC",),
            Result.TRAJECTORY: ("ADMP", "BOMD", "TRJ-TRJ"),
            Result.PCM_CAVITY: ("PCM", "Polarizable Continuum Model"),
        }.get(self, ())

    @property
    def intermediate_geometries(self):
        return self in (Result.OPTIMIZATION, Result.IRC, Result.SCAN, Result.TRAJECTORY)


class SurfaceStyle(Enum):
    SOLID = "Solid"
    TRANSPARENT = "Transparent"
    MESH = "Mesh"


@dataclass(frozen=True)
class Alignment:
    """Signed molecular axes to place horizontally and vertically in the view."""

    horizontal: str = "X"
    vertical: str = "Y"

    def __post_init__(self):
        axes = {"X", "Y", "Z", "-X", "-Y", "-Z"}
        if self.horizontal not in axes or self.vertical not in axes:
            raise ValueError("Alignment axes must be X, Y, Z, -X, -Y or -Z")
        if self.horizontal.lstrip("-") == self.vertical.lstrip("-"):
            raise ValueError("Horizontal and vertical axes must be orthogonal")

    @property
    def pairs(self):
        return ((self.horizontal, "X"), (self.vertical, "Y"))


class Grouping(Enum):
    SEPARATE = "Separate new molecule group for each file"
    TOGETHER = "Single new molecule group for all files"


class Layout(Enum):
    OVERLAP = "overlap"
    CASCADE = "cascade"
    TILE = "tile"


@dataclass(frozen=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self):
        import math

        if not all(math.isfinite(v) for v in (self.x, self.y, self.width, self.height)):
            raise ValueError("Window bounds must be finite")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Window dimensions must be positive")

    @classmethod
    def from_window(cls, window):
        value = window["kCGWindowBounds"]
        return cls(*(round(value[key]) for key in ("X", "Y", "Width", "Height")))


@dataclass(frozen=True)
class Screen:
    identifier: int
    name: str
    bounds: Bounds
    work_area: Bounds


@dataclass(frozen=True)
class Surface:
    """Named density/ESP cube pair with explicitly labeled file arguments."""

    name: str
    density: Path = field(kw_only=True)
    potential: Path = field(kw_only=True)


@dataclass(frozen=True)
class Workflow:
    source: Path
    results: tuple[Result, ...] = ()
    surfaces: tuple[Surface, ...] = ()
    density_isovalue: float = 0.002
    alignment: Alignment | None = None
    surface_style: SurfaceStyle = SurfaceStyle.TRANSPARENT
    opacity: float = 0.5
    # Entries: role (surface name, "source", "plot", or a Result), position, size.
    layout: tuple[tuple[str | Result, tuple[int, int], tuple[int, int]], ...] = ()
    reference_screen: tuple[int, int] = (1728, 1117)
    position_jitter: int = 8
    size_jitter: int = 6

    @property
    def files(self):
        return (
            self.source,
            *(p for s in self.surfaces for p in (s.density, s.potential)),
        )

    def validate(self):
        """Validate required files and result markers without opening GaussView.

        Raises ValueError for missing data or invalid workflow settings.
        """
        from .viewer import validate

        validate(self)

    def view(
        self,
        *,
        application_path: Path | str | None = None,
        reuse_views: bool = True,
        log_level: int | str = "INFO",
    ):
        """Open this workflow in GaussView.

        Args:
            application_path: Application bundle; defaults to ~/Applications/GaussView6/gview.app.
            reuse_views: Reuse loaded data and restore missing panels; False reloads files.
            log_level: Standard logging level, such as "INFO", "DEBUG" or logging.DEBUG.

        Validates the workflow before opening windows. Failures raise their original
        exceptions for the caller to handle. Reuse preserves already loaded data;
        use reuse_views=False after changing source or cube files.
        Process arguments are never inspected.
        """
        from .viewer import open_workflow

        return open_workflow(
            self, application_path=application_path, reuse_views=reuse_views, log_level=log_level
        )
