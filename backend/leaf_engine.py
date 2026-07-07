"""
CropGuard AI — chrysanthemum leaf disease detection (3-class model).
Separate from the main plantation ai_engine.py.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from PIL import Image

try:
    import torch
    import torch.nn as nn
    from torchvision import transforms
    from torchvision.models import mobilenet_v2

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None
    transforms = None
    mobilenet_v2 = None

BACKEND_DIR = Path(__file__).resolve().parent
IMAGE_SIZE = 224
DROPOUT = 0.3
PROBLEM_CLASSES = {"Bacterial", "Septoria"}

MODEL_SEARCH_PATHS = [
    BACKEND_DIR / "models" / "chrysanthemum_leaf_model.pth",
    BACKEND_DIR / "chrysanthemum_leaf_model.pth",
    Path("/tmp/chrysanthemum_leaf_model.pth"),
]

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

CLASS_INFO = {
    "Healthy": {
        "description": "No disease detected. Plant appears healthy.",
        "recommendation": "Continue regular monitoring and watering schedule.",
    },
    "Bacterial": {
        "description": "Bacterial infection detected on leaf tissue.",
        "recommendation": (
            "Apply copper-based bactericide. Remove severely affected leaves. "
            "Avoid overhead watering to reduce spread."
        ),
    },
    "Septoria": {
        "description": "Septoria leaf spot detected (fungal disease).",
        "recommendation": (
            "Apply appropriate fungicide. Improve air circulation. "
            "Remove and destroy affected leaves. Avoid wetting foliage."
        ),
    },
}

_leaf_bundle = None
leaf_model_loaded = False
leaf_model_path_used: Path | None = None


def _class_names_from_checkpoint(checkpoint: dict) -> list[str]:
    if checkpoint.get("class_to_idx"):
        class_to_idx = checkpoint["class_to_idx"]
        return [name for name, _ in sorted(class_to_idx.items(), key=lambda x: x[1])]
    return list(checkpoint.get("class_names", []))


def _resolve_model_path() -> Path | None:
    env_path = os.getenv("CROPGUARD_LEAF_MODEL_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return candidate
    for candidate in MODEL_SEARCH_PATHS:
        if candidate.is_file():
            return candidate
    return None


def _build_transform(image_size: int = IMAGE_SIZE) -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize(256),
            transforms.CenterCrop(image_size),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )


def load_leaf_engine() -> dict | None:
    """Load the 3-class chrysanthemum leaf model."""
    global _leaf_bundle, leaf_model_loaded, leaf_model_path_used

    if not TORCH_AVAILABLE:
        leaf_model_loaded = False
        leaf_model_path_used = None
        _leaf_bundle = None
        return None

    if _leaf_bundle is not None:
        return _leaf_bundle

    model_path = _resolve_model_path()
    leaf_model_path_used = model_path
    if model_path is None:
        leaf_model_loaded = False
        _leaf_bundle = None
        return None

    try:
        device = torch.device("cpu")
        checkpoint = torch.load(model_path, map_location=device, weights_only=False)
        class_names = _class_names_from_checkpoint(checkpoint)
        class_to_idx = checkpoint.get("class_to_idx") or {
            name: idx for idx, name in enumerate(class_names)
        }
        num_classes = checkpoint.get("num_classes", len(class_names))
        image_size = checkpoint.get("image_size", IMAGE_SIZE)

        model = mobilenet_v2(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier = nn.Sequential(
            nn.Dropout(p=DROPOUT),
            nn.Linear(in_features, num_classes),
        )
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(device)
        model.eval()

        _leaf_bundle = {
            "model": model,
            "transform": _build_transform(image_size),
            "class_names": class_names,
            "class_to_idx": class_to_idx,
            "device": device,
            "path": model_path,
        }
        leaf_model_loaded = True
        print(f"Leaf model loaded: {model_path} (classes: {class_names})")
        return _leaf_bundle
    except Exception as exc:
        leaf_model_loaded = False
        leaf_model_path_used = None
        _leaf_bundle = None
        print(f"Leaf model failed to load: {exc}")
        return None


def get_leaf_model_status() -> dict:
    if not TORCH_AVAILABLE:
        return {"loaded": False, "path": None, "error": "PyTorch not available"}
    if _leaf_bundle is not None and leaf_model_path_used is not None:
        return {
            "loaded": True,
            "path": str(leaf_model_path_used),
            "classes": _leaf_bundle["class_names"],
            "class_to_idx": _leaf_bundle.get("class_to_idx"),
        }
    resolved = _resolve_model_path()
    if resolved is None:
        return {"loaded": False, "path": None, "error": "Leaf model file not found"}
    load_leaf_engine()
    if leaf_model_loaded and leaf_model_path_used is not None:
        return {
            "loaded": True,
            "path": str(leaf_model_path_used),
            "classes": _leaf_bundle["class_names"],
            "class_to_idx": _leaf_bundle.get("class_to_idx"),
        }
    return {"loaded": False, "path": str(resolved), "error": "Leaf model failed to load"}


def _unavailable_result() -> dict:
    return {
        "class": "unavailable",
        "message": "Leaf model not loaded",
    }


def predict_leaf_bytes(image_bytes: bytes) -> dict:
    """Run leaf disease inference on raw image bytes."""
    if not image_bytes:
        raise ValueError("Empty image data")

    if not TORCH_AVAILABLE:
        return _unavailable_result()

    bundle = load_leaf_engine()
    if bundle is None:
        return _unavailable_result()

    model = bundle["model"]
    transform = bundle["transform"]
    device = bundle["device"]
    class_names = bundle["class_names"]

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError(f"Could not decode image: {exc}") from exc

    with torch.no_grad():
        tensor = transform(image).unsqueeze(0).to(device)
        probs = torch.nn.functional.softmax(model(tensor), dim=1)[0]
        conf, idx = torch.max(probs, dim=0)
        class_name = class_names[int(idx.item())]
        confidence = round(float(conf.item()) * 100, 2)

    info = CLASS_INFO.get(
        class_name,
        {
            "description": f"Classification result: {class_name}",
            "recommendation": "Consult an agronomist for treatment guidance.",
        },
    )

    return {
        "class": class_name,
        "confidence": confidence,
        "is_problem": class_name in PROBLEM_CLASSES,
        "description": info["description"],
        "recommendation": info["recommendation"],
    }
