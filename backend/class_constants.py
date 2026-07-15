"""Shared 3-class leaf disease constants for CropGuard AI."""

PROBLEM_CLASSES = {"Bacterial", "Septoria"}
HEALTHY_CLASS = "Healthy"
CANONICAL_CLASSES = ("Bacterial", "Healthy", "Septoria")

# Map legacy 4-class labels → new 3-class taxonomy (for old DB rows / seeds)
LEGACY_CLASS_MAP = {
    "healthy": "Healthy",
    "diseased": "Bacterial",
    "pest_affected": "Bacterial",
    "pest": "Bacterial",
    "water_stressed": "Septoria",
    "bacterial": "Bacterial",
    "septoria": "Septoria",
}


def normalize_class(cls: str | None) -> str:
    if not cls:
        return ""
    if cls in PROBLEM_CLASSES or cls == HEALTHY_CLASS:
        return cls
    mapped = LEGACY_CLASS_MAP.get(cls.lower().strip())
    if mapped:
        return mapped
    # Title-case known names
    title = cls[:1].upper() + cls[1:]
    if title in PROBLEM_CLASSES or title == HEALTHY_CLASS:
        return title
    return cls


def is_healthy(cls: str | None) -> bool:
    return normalize_class(cls) == HEALTHY_CLASS


def is_problem(cls: str | None) -> bool:
    return normalize_class(cls) in PROBLEM_CLASSES


def empty_class_counts() -> dict[str, int]:
    return {name: 0 for name in CANONICAL_CLASSES}
