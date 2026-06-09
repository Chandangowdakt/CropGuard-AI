"""
CropGuard AI — chrysanthemum disease detection engine.
Loads fine-tuned MobileNetV2 from the plantation AI project.
"""

import io
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

import os

from PIL import Image

try:
    import torch
    import torch.nn as nn
    import torchvision
    from torchvision import transforms
    from torchvision.models import mobilenet_v2
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None
    transforms = None
    mobilenet_v2 = None

CLASS_NAMES = ["healthy", "diseased", "pest_affected", "water_stressed"]
PROBLEM_CLASSES = {"diseased", "pest_affected", "water_stressed"}
CONFIDENCE_THRESHOLD = 75.0
LOW_CONFIDENCE_MESSAGE = "Low confidence — please take a clearer close-up photo of the leaf"
MODEL_UNAVAILABLE_MESSAGE = "AI model not loaded. Please upload the model file."
SERVER_UNAVAILABLE_MESSAGE = "AI model not available on server. Use local version for predictions."
IMAGE_SIZE = 224

BACKEND_DIR = Path(__file__).resolve().parent
MODEL_SEARCH_PATHS = [
    Path("/tmp/chrysanthemum_model.pth"),
    BACKEND_DIR / "chrysanthemum_model.pth",
    Path("chrysanthemum_model.pth"),
]

_bundle = None
model_loaded = False
model_path_used: Path | None = None
_resolved_path: Path | None = None

if not TORCH_AVAILABLE:
    model_loaded = False
    model_path_used = None
    print("PyTorch not available - AI predictions disabled")


class ModelNotFoundError(FileNotFoundError):
    """Raised when chrysanthemum_model.pth is missing."""


class ModelLoadError(RuntimeError):
    """Raised when the checkpoint cannot be loaded."""


def _resolve_model_path() -> Path | None:
    env_path = os.getenv("CROPGUARD_MODEL_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate
    for candidate in MODEL_SEARCH_PATHS:
        if candidate.exists():
            return candidate
    return None


def _build_transform(image_size: int = IMAGE_SIZE):
    """Same validation transforms as phase4_train.py (no augmentation)."""
    return transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def load_engine() -> dict | None:
    global _bundle, model_loaded, _resolved_path, model_path_used
    if not TORCH_AVAILABLE:
        model_loaded = False
        model_path_used = None
        _resolved_path = None
        return None

    if _bundle is not None:
        return _bundle

    _resolved_path = _resolve_model_path()
    model_path_used = _resolved_path
    if _resolved_path is None:
        model_loaded = False
        model_path_used = None
        return None

    try:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        checkpoint = torch.load(_resolved_path, map_location=device, weights_only=False)

        class_names = checkpoint.get("class_names", CLASS_NAMES)
        num_classes = checkpoint.get("num_classes", len(class_names))
        image_size = checkpoint.get("image_size", IMAGE_SIZE)

        model = mobilenet_v2(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(device)
        model.eval()

        _bundle = {
            "model": model,
            "transform": _build_transform(image_size),
            "class_names": class_names,
            "device": device,
        }
        model_loaded = True
        return _bundle
    except Exception as e:
        model_loaded = False
        model_path_used = None
        _bundle = None
        raise ModelLoadError(f"Failed to load model from {_resolved_path}: {e}") from e


def get_model_status() -> dict:
    """Return whether the AI model is loaded and where it was found."""
    global model_loaded, _resolved_path, model_path_used
    if not TORCH_AVAILABLE:
        return {"loaded": False, "path": None}

    if _bundle is not None and _resolved_path is not None:
        return {"loaded": True, "path": str(_resolved_path)}

    resolved = _resolve_model_path()
    if resolved is None:
        model_loaded = False
        model_path_used = None
        _resolved_path = None
        return {"loaded": False, "path": None}

    try:
        load_engine()
        if model_loaded and _resolved_path is not None:
            return {"loaded": True, "path": str(_resolved_path)}
    except ModelLoadError:
        pass

    return {"loaded": False, "path": str(resolved)}


def _unavailable_result(message: str = MODEL_UNAVAILABLE_MESSAGE) -> dict:
    return {
        "class": "unavailable",
        "confidence": 0,
        "is_problem": False,
        "message": message,
    }


def _format_result(class_name: str, confidence: float) -> dict:
    return {
        "class": class_name,
        "confidence": confidence,
        "is_problem": class_name in PROBLEM_CLASSES,
    }


def _predict_pil(image: Image.Image) -> dict:
    bundle = load_engine()
    if bundle is None:
        return _unavailable_result()

    model = bundle["model"]
    transform = bundle["transform"]
    device = bundle["device"]
    class_names = bundle["class_names"]

    with torch.no_grad():
        tensor = transform(image.convert("RGB")).unsqueeze(0).to(device)
        probs = torch.nn.functional.softmax(model(tensor), dim=1)[0]
        conf, idx = torch.max(probs, dim=0)
        class_name = class_names[int(idx.item())]
        confidence = round(float(conf.item()) * 100, 2)
    return _format_result(class_name, confidence)


def predict_image(image_path: str | Path) -> dict:
    """
    Run inference on an image file.

    Returns:
        {"class": "diseased", "confidence": 99.7, "is_problem": true}
    """
    if not TORCH_AVAILABLE or not model_loaded:
        load_engine()
    if not TORCH_AVAILABLE:
        return _unavailable_result(SERVER_UNAVAILABLE_MESSAGE)

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    try:
        image = Image.open(path)
        raw = _predict_pil(image)
        if raw.get("class") == "unavailable":
            return raw
        return raw
    except ModelLoadError:
        raise
    except Exception as e:
        raise ValueError(f"Could not read image {path}: {e}") from e


def predict_image_bytes(image_bytes: bytes) -> dict:
    """
    Run inference on raw image bytes (for API uploads).

    Returns:
        {
            "class": "diseased" | "uncertain" | "unavailable",
            "actual_class": "diseased",
            "confidence": 99.7,
            "is_problem": true,
            "message": "...optional warning...",
        }
    """
    if not image_bytes:
        raise ValueError("Empty image data")

    if not TORCH_AVAILABLE:
        return _unavailable_result(SERVER_UNAVAILABLE_MESSAGE)

    if load_engine() is None or not model_loaded:
        return _unavailable_result(SERVER_UNAVAILABLE_MESSAGE)

    try:
        image = Image.open(io.BytesIO(image_bytes))
        raw = _predict_pil(image)
        if raw.get("class") == "unavailable":
            return raw

        actual_class = raw["class"]
        confidence = raw["confidence"]

        result = {
            "actual_class": actual_class,
            "confidence": confidence,
        }

        if confidence < CONFIDENCE_THRESHOLD:
            result.update({
                "class": "uncertain",
                "is_problem": False,
                "message": LOW_CONFIDENCE_MESSAGE,
            })
        else:
            result.update({
                "class": actual_class,
                "is_problem": actual_class in PROBLEM_CLASSES,
            })

        return result
    except ModelLoadError:
        return _unavailable_result(SERVER_UNAVAILABLE_MESSAGE)
    except Exception as e:
        raise ValueError(f"Could not decode image bytes: {e}") from e


def model_status() -> dict:
    """Backward-compatible status helper used by main.py health checks."""
    status = get_model_status()
    if not status["loaded"]:
        error = SERVER_UNAVAILABLE_MESSAGE if not TORCH_AVAILABLE else MODEL_UNAVAILABLE_MESSAGE
        return {
            "loaded": False,
            "path": status.get("path"),
            "error": error,
        }
    try:
        bundle = load_engine()
        if bundle is None:
            return {
                "loaded": False,
                "path": status.get("path"),
                "error": MODEL_UNAVAILABLE_MESSAGE,
            }
        return {
            "loaded": True,
            "path": status["path"],
            "classes": bundle["class_names"],
            "device": str(bundle["device"]),
        }
    except ModelLoadError as e:
        return {"loaded": False, "path": status.get("path"), "error": str(e)}
