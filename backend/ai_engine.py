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

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms
from torchvision.models import mobilenet_v2

CLASS_NAMES = ["healthy", "diseased", "pest_affected", "water_stressed"]
PROBLEM_CLASSES = {"diseased", "pest_affected", "water_stressed"}
CONFIDENCE_THRESHOLD = 75.0
LOW_CONFIDENCE_MESSAGE = "Low confidence — please take a clearer close-up photo of the leaf"
IMAGE_SIZE = 224

# Trained model (override with CROPGUARD_MODEL_PATH env var)
DEFAULT_MODEL_PATH = Path(
    r"C:\Users\ktcha\Downloads\ai engine\chrysanthemum_ai\models\chrysanthemum_model.pth"
)
MODEL_PATH = Path(os.getenv("CROPGUARD_MODEL_PATH", str(DEFAULT_MODEL_PATH)))

_bundle = None


class ModelNotFoundError(FileNotFoundError):
    """Raised when chrysanthemum_model.pth is missing."""


class ModelLoadError(RuntimeError):
    """Raised when the checkpoint cannot be loaded."""


def _build_transform(image_size: int = IMAGE_SIZE) -> transforms.Compose:
    """Same validation transforms as phase4_train.py (no augmentation)."""
    return transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def load_engine() -> dict:
    global _bundle
    if _bundle is not None:
        return _bundle

    if not MODEL_PATH.exists():
        raise ModelNotFoundError(
            f"Chrysanthemum model not found at:\n  {MODEL_PATH}\n\n"
            "Train the model first (phase4_train.py) or set CROPGUARD_MODEL_PATH."
        )

    try:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        checkpoint = torch.load(MODEL_PATH, map_location=device, weights_only=False)

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
        return _bundle
    except ModelNotFoundError:
        raise
    except Exception as e:
        raise ModelLoadError(f"Failed to load model from {MODEL_PATH}: {e}") from e


def _format_result(class_name: str, confidence: float) -> dict:
    return {
        "class": class_name,
        "confidence": confidence,
        "is_problem": class_name in PROBLEM_CLASSES,
    }


@torch.no_grad()
def _predict_pil(image: Image.Image) -> dict:
    bundle = load_engine()
    model = bundle["model"]
    transform = bundle["transform"]
    device = bundle["device"]
    class_names = bundle["class_names"]

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
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    try:
        image = Image.open(path)
        return _predict_pil(image)
    except (ModelNotFoundError, ModelLoadError):
        raise
    except Exception as e:
        raise ValueError(f"Could not read image {path}: {e}") from e


def predict_image_bytes(image_bytes: bytes) -> dict:
    """
    Run inference on raw image bytes (for API uploads).

    Returns:
        {
            "class": "diseased" | "uncertain",
            "actual_class": "diseased",
            "confidence": 99.7,
            "is_problem": true,
            "message": "...optional low-confidence warning...",
        }
    """
    if not image_bytes:
        raise ValueError("Empty image data")
    try:
        image = Image.open(io.BytesIO(image_bytes))
        raw = _predict_pil(image)
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
    except (ModelNotFoundError, ModelLoadError):
        raise
    except Exception as e:
        raise ValueError(f"Could not decode image bytes: {e}") from e


def model_status() -> dict:
    try:
        bundle = load_engine()
        return {
            "loaded": True,
            "path": str(MODEL_PATH.resolve()),
            "classes": bundle["class_names"],
            "device": str(bundle["device"]),
        }
    except ModelNotFoundError as e:
        return {"loaded": False, "path": str(MODEL_PATH), "error": str(e)}
    except ModelLoadError as e:
        return {"loaded": False, "path": str(MODEL_PATH), "error": str(e)}
