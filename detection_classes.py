"""Shared class names and source-folder mapping for waste object detection."""

from pathlib import Path

CLASSES = [
    "organic",
    "plastic",
    "plastic_bottle",
    "cans",
    "glass",
    "paper",
    "other_non_biodegradable",
    "residual_special_waste",
]

BIN_BY_CLASS = {
    "organic": "biodegradable",
    "plastic": "non_biodegradable",
    "plastic_bottle": "non_biodegradable",
    "cans": "non_biodegradable",
    "glass": "non_biodegradable",
    "paper": "non_biodegradable",
    "other_non_biodegradable": "non_biodegradable",
    "residual_special_waste": "residual_special_waste",
}

FOLDER_TO_CLASS = {
    "food scraps": "organic",
    "fruit peels": "organic",
    "organic": "organic",
    "plastic": "plastic",
    "plastic bottles": "plastic_bottle",
    "cans": "cans",
    "glass": "glass",
    "paper": "paper",
    "residual": "residual_special_waste",
    "residual_special_waste": "residual_special_waste",
    "biodegradable": "organic",
    "non_biodegradable": "other_non_biodegradable",
}


def class_id_for_image(image_path, source=Path("public")):
    """Infer a reviewable default label from the closest recognized folder."""
    relative = Path(image_path).relative_to(source)
    for part in reversed(relative.parts[:-1]):
        name = FOLDER_TO_CLASS.get(part.strip().lower())
        if name is not None:
            return CLASSES.index(name)
    raise ValueError(f"No detection class mapping for image: {image_path}")
