"""Single source of truth for the 3 waste classes (one class per bin)."""

from pathlib import Path

CLASSES = [
    "biodegradable",
    "non_biodegradable",
    "residual_special_waste",
]

# Each class is its own bin (kept so older code that imports it still works)
BIN_BY_CLASS = {name: name for name in CLASSES}


def class_id_for_image(path, source):
    """Class ID comes from the top-level folder under `source` (public/).
    Subfolders like 'Food scraps', 'cans', 'glass' are ignored."""
    parts = Path(path).relative_to(source).parts
    if len(parts) < 2:
        raise ValueError(f"Image is not inside a class folder: {path}")
    top = parts[0].lower()
    if top not in CLASSES:
        raise ValueError(f"No class mapping for {path}")
    return CLASSES.index(top)