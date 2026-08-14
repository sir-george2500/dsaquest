"""The Codex — who the masters are, and what they can see in you."""

from .diagnosis import FALLBACK, GAP, MIN_EVIDENCE, Diagnosis, Weakness, diagnose
from .lore import Depth, Entry, MasterLore, Relationship, depth_reached, diagnosis_line, load_lore
from .reading import Reading, read_student

__all__ = [
    "FALLBACK",
    "GAP",
    "MIN_EVIDENCE",
    "Depth",
    "Diagnosis",
    "Entry",
    "MasterLore",
    "Reading",
    "Relationship",
    "Weakness",
    "depth_reached",
    "diagnose",
    "diagnosis_line",
    "load_lore",
    "read_student",
]
