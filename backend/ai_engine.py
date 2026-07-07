"""
CropGuard AI — chrysanthemum disease detection engine.
Loads fine-tuned MobileNetV2 from the plantation AI project.

Live model: returned to users (unchanged).
Shadow model v2: runs in parallel, logged only — never shown to users.
"""

import csv
import hashlib
import io
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
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
    import torchvision
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
    print("WARNING: PyTorch not available — AI predictions disabled")

CLASS_NAMES = ["healthy", "diseased", "pest_affected", "water_stressed"]
PROBLEM_CLASSES = {"diseased", "pest_affected", "water_stressed"}
CONFIDENCE_THRESHOLD = 75.0
LOW_CONFIDENCE_MESSAGE = "Low confidence — please take a clearer close-up photo of the leaf"
MODEL_UNAVAILABLE_MESSAGE = "AI model not loaded. Please upload the model file."
SERVER_UNAVAILABLE_MESSAGE = "AI model not available on server. Use local version for predictions."
IMAGE_SIZE = 224
V2_DROPOUT = 0.3

BACKEND_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BACKEND_DIR / "storage"
SHADOW_PREDICTIONS_CSV = STORAGE_DIR / "shadow_predictions.csv"
SHADOW_CSV_COLUMNS = [
    "timestamp",
    "image_id",
    "live_prediction",
    "live_confidence",
    "v2_prediction",
    "v2_confidence",
    "agree",
]

DEFAULT_MODEL_DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/Chandangowdakt/CropGuard-AI/main/"
    "backend/chrysanthemum_model.pth"
)
DEFAULT_MODEL_DEST = BACKEND_DIR / "chrysanthemum_model.pth"
MIN_MODEL_BYTES = 5_000_000

MODEL_SEARCH_PATHS = [
    Path("/tmp/chrysanthemum_model.pth"),
    BACKEND_DIR / "chrysanthemum_model.pth",
    BACKEND_DIR / "models" / "chrysanthemum_model.pth",
    Path("chrysanthemum_model.pth"),
]

SHADOW_MODEL_SEARCH_PATHS = [
    BACKEND_DIR / "models" / "chrysanthemum_model_v2.pth",
]

_live_bundle = None
_shadow_bundle = None
model_loaded = False
shadow_model_loaded = False
model_path_used: Path | None = None
shadow_model_path_used: Path | None = None
_resolved_path: Path | None = None
_shadow_resolved_path: Path | None = None

# Backward-compatible alias used by existing imports
_bundle = None

if not TORCH_AVAILABLE:
    model_loaded = False
    shadow_model_loaded = False
    model_path_used = None
    shadow_model_path_used = None


class ModelNotFoundError(FileNotFoundError):
    """Raised when chrysanthemum_model.pth is missing."""


class ModelLoadError(RuntimeError):
    """Raised when the checkpoint cannot be loaded."""


def _is_valid_model_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size >= MIN_MODEL_BYTES


def _resolve_model_path() -> Path | None:
    env_path = os.getenv("CROPGUARD_MODEL_PATH")
    if env_path:
        candidate = Path(env_path)
        if _is_valid_model_file(candidate):
            return candidate
    for candidate in MODEL_SEARCH_PATHS:
        if _is_valid_model_file(candidate):
            return candidate
    return None


def ensure_model_available() -> Path | None:
    """
    Ensure the live production model exists on disk.

    On Render the .pth file is not in the repo history by default; download it once
    from GitHub (or CROPGUARD_MODEL_URL) before inference.
    """
    existing = _resolve_model_path()
    if existing is not None:
        return existing

    url = os.getenv("CROPGUARD_MODEL_URL", DEFAULT_MODEL_DOWNLOAD_URL)
    dest = DEFAULT_MODEL_DEST
    if _is_valid_model_file(dest):
        return dest

    try:
        print(f"Downloading chrysanthemum_model.pth from {url} ...")
        dest.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "CropGuard-AI/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        if len(data) < MIN_MODEL_BYTES:
            raise ModelLoadError(
                f"Downloaded model is too small ({len(data)} bytes) — check CROPGUARD_MODEL_URL"
            )
        dest.write_bytes(data)
        print(f"Model saved to {dest} ({len(data):,} bytes)")
        return dest
    except (urllib.error.URLError, OSError, ModelLoadError) as e:
        print(f"Model download failed: {e}")
        return None


def _resolve_shadow_model_path() -> Path | None:
    env_path = os.getenv("CROPGUARD_SHADOW_MODEL_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate
    for candidate in SHADOW_MODEL_SEARCH_PATHS:
        if candidate.exists():
            return candidate
    return None


def _class_names_from_checkpoint(checkpoint: dict) -> list[str]:
    if checkpoint.get("class_to_idx"):
        class_to_idx = checkpoint["class_to_idx"]
        return [name for name, _ in sorted(class_to_idx.items(), key=lambda x: x[1])]
    return list(checkpoint.get("class_names", CLASS_NAMES))


def _build_transform(image_size: int = IMAGE_SIZE):
    """Same validation transforms as phase4_train.py (no augmentation)."""
    return transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def _load_live_checkpoint(path: Path, device: torch.device) -> dict:
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    class_names = _class_names_from_checkpoint(checkpoint)
    num_classes = checkpoint.get("num_classes", len(class_names))
    image_size = checkpoint.get("image_size", IMAGE_SIZE)

    model = mobilenet_v2(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, num_classes)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    return {
        "model": model,
        "transform": _build_transform(image_size),
        "class_names": class_names,
        "class_to_idx": checkpoint.get("class_to_idx"),
        "device": device,
        "path": path,
        "variant": "live",
    }


def _load_shadow_checkpoint(path: Path, device: torch.device) -> dict:
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    class_names = _class_names_from_checkpoint(checkpoint)
    num_classes = checkpoint.get("num_classes", len(class_names))
    image_size = checkpoint.get("image_size", IMAGE_SIZE)

    model = mobilenet_v2(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=V2_DROPOUT),
        nn.Linear(in_features, num_classes),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    return {
        "model": model,
        "transform": _build_transform(image_size),
        "class_names": class_names,
        "class_to_idx": checkpoint.get("class_to_idx"),
        "device": device,
        "path": path,
        "variant": "shadow_v2",
    }


def load_engine() -> dict | None:
    """Load the live model used for all user-facing predictions."""
    global _live_bundle, _bundle, model_loaded, _resolved_path, model_path_used
    if not TORCH_AVAILABLE:
        model_loaded = False
        model_path_used = None
        _resolved_path = None
        _live_bundle = None
        _bundle = None
        return None

    if _live_bundle is not None:
        return _live_bundle

    _resolved_path = _resolve_model_path()
    model_path_used = _resolved_path
    if _resolved_path is None:
        model_loaded = False
        model_path_used = None
        return None

    try:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        _live_bundle = _load_live_checkpoint(_resolved_path, device)
        _bundle = _live_bundle
        model_loaded = True
        return _live_bundle
    except Exception as e:
        model_loaded = False
        model_path_used = None
        _live_bundle = None
        _bundle = None
        raise ModelLoadError(f"Failed to load model from {_resolved_path}: {e}") from e


def load_shadow_engine() -> dict | None:
    """Load shadow v2 model (logging only — never returned to users)."""
    global _shadow_bundle, shadow_model_loaded, _shadow_resolved_path, shadow_model_path_used
    if not TORCH_AVAILABLE:
        shadow_model_loaded = False
        shadow_model_path_used = None
        _shadow_resolved_path = None
        _shadow_bundle = None
        return None

    if _shadow_bundle is not None:
        return _shadow_bundle

    _shadow_resolved_path = _resolve_shadow_model_path()
    shadow_model_path_used = _shadow_resolved_path
    if _shadow_resolved_path is None:
        shadow_model_loaded = False
        shadow_model_path_used = None
        return None

    try:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        _shadow_bundle = _load_shadow_checkpoint(_shadow_resolved_path, device)
        shadow_model_loaded = True
        print(f"Shadow model v2 loaded (logging only): {_shadow_resolved_path}")
        return _shadow_bundle
    except Exception as e:
        shadow_model_loaded = False
        shadow_model_path_used = None
        _shadow_bundle = None
        print(f"Shadow model v2 not loaded: {e}")
        return None


def load_all_engines() -> None:
    """Load live and shadow models on startup / first prediction."""
    ensure_model_available()
    load_engine()
    load_shadow_engine()


def get_model_status() -> dict:
    """Return whether the live AI model is loaded and where it was found."""
    global model_loaded, _resolved_path, model_path_used
    if not TORCH_AVAILABLE:
        return {"loaded": False, "path": None}

    if _live_bundle is not None and _resolved_path is not None:
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


def get_shadow_model_status() -> dict:
    """Shadow v2 model status (not used for user responses)."""
    if not TORCH_AVAILABLE:
        return {"loaded": False, "path": None}
    if _shadow_bundle is not None and _shadow_resolved_path is not None:
        return {
            "loaded": True,
            "path": str(_shadow_resolved_path),
            "class_names": _shadow_bundle["class_names"],
            "class_to_idx": _shadow_bundle.get("class_to_idx"),
        }
    resolved = _resolve_shadow_model_path()
    if resolved is None:
        return {"loaded": False, "path": None}
    load_shadow_engine()
    if shadow_model_loaded and _shadow_resolved_path is not None:
        return {
            "loaded": True,
            "path": str(_shadow_resolved_path),
            "class_names": _shadow_bundle["class_names"],
            "class_to_idx": _shadow_bundle.get("class_to_idx"),
        }
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


def _predict_with_bundle(bundle: dict, image: Image.Image) -> dict | None:
    if bundle is None:
        return None

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


def _predict_pil(image: Image.Image) -> dict:
    bundle = load_engine()
    if bundle is None:
        return _unavailable_result()
    result = _predict_with_bundle(bundle, image)
    return result if result is not None else _unavailable_result()


def _image_id_from_bytes(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()[:16]


def _ensure_shadow_csv() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    if not SHADOW_PREDICTIONS_CSV.exists():
        with SHADOW_PREDICTIONS_CSV.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=SHADOW_CSV_COLUMNS).writeheader()


def _log_shadow_prediction(
    image_id: str,
    live_prediction: str,
    live_confidence: float,
    v2_prediction: str,
    v2_confidence: float,
) -> None:
    _ensure_shadow_csv()
    agree = live_prediction == v2_prediction
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "image_id": image_id,
        "live_prediction": live_prediction,
        "live_confidence": f"{live_confidence:.2f}",
        "v2_prediction": v2_prediction,
        "v2_confidence": f"{v2_confidence:.2f}",
        "agree": str(agree).lower(),
    }
    with SHADOW_PREDICTIONS_CSV.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=SHADOW_CSV_COLUMNS).writerow(row)


def _run_shadow_comparison(image: Image.Image, image_bytes: bytes, live_raw: dict) -> None:
    """Run shadow v2 and log side-by-side; never affects user response."""
    if live_raw.get("class") == "unavailable":
        return

    shadow = load_shadow_engine()
    if shadow is None:
        return

    try:
        v2_raw = _predict_with_bundle(shadow, image)
        if v2_raw is None:
            return
        live_class = live_raw.get("actual_class") or live_raw.get("class")
        _log_shadow_prediction(
            image_id=_image_id_from_bytes(image_bytes),
            live_prediction=live_class,
            live_confidence=float(live_raw.get("confidence", 0)),
            v2_prediction=v2_raw["class"],
            v2_confidence=float(v2_raw["confidence"]),
        )
    except Exception as e:
        print(f"Shadow prediction log failed (live result unchanged): {e}")


def get_shadow_comparison_stats() -> dict:
    """Aggregate stats from shadow_predictions.csv for admin dashboard."""
    if not SHADOW_PREDICTIONS_CSV.exists():
        return {
            "total_predictions": 0,
            "agreements": 0,
            "disagreements": 0,
            "agreement_rate": None,
            "disagreement_breakdown": {},
            "disagreement_pairs": {},
            "shadow_model": get_shadow_model_status(),
            "csv_path": str(SHADOW_PREDICTIONS_CSV),
        }

    total = 0
    agreements = 0
    disagreement_by_live: dict[str, int] = {}
    disagreement_pairs: dict[str, int] = {}

    with SHADOW_PREDICTIONS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            agree = row.get("agree", "").lower() == "true"
            if agree:
                agreements += 1
                continue

            live_cls = row.get("live_prediction", "unknown")
            v2_cls = row.get("v2_prediction", "unknown")
            disagreement_by_live[live_cls] = disagreement_by_live.get(live_cls, 0) + 1
            pair_key = f"{live_cls} -> {v2_cls}"
            disagreement_pairs[pair_key] = disagreement_pairs.get(pair_key, 0) + 1

    disagreements = total - agreements
    agreement_rate = round(agreements / total, 4) if total else None

    return {
        "total_predictions": total,
        "agreements": agreements,
        "disagreements": disagreements,
        "agreement_rate": agreement_rate,
        "agreement_rate_pct": round(agreement_rate * 100, 2) if agreement_rate is not None else None,
        "disagreement_breakdown": dict(
            sorted(disagreement_by_live.items(), key=lambda x: -x[1])
        ),
        "disagreement_pairs": dict(
            sorted(disagreement_pairs.items(), key=lambda x: -x[1])
        ),
        "shadow_model": get_shadow_model_status(),
        "csv_path": str(SHADOW_PREDICTIONS_CSV),
    }


def predict_image(image_path: str | Path) -> dict:
    """
    Run inference on an image file.

    Returns:
        {"class": "diseased", "confidence": 99.7, "is_problem": true}
    """
    if not TORCH_AVAILABLE or not model_loaded:
        load_all_engines()
    if not TORCH_AVAILABLE:
        return _unavailable_result(SERVER_UNAVAILABLE_MESSAGE)

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    try:
        image_bytes = path.read_bytes()
        image = Image.open(io.BytesIO(image_bytes))
        raw = _predict_pil(image)
        if raw.get("class") != "unavailable":
            raw_with_actual = {**raw, "actual_class": raw["class"]}
            _run_shadow_comparison(image, image_bytes, raw_with_actual)
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

    load_all_engines()
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

        _run_shadow_comparison(image, image_bytes, result)
        return result
    except ModelLoadError:
        return _unavailable_result(SERVER_UNAVAILABLE_MESSAGE)
    except Exception as e:
        raise ValueError(f"Could not decode image bytes: {e}") from e


def model_status() -> dict:
    """Backward-compatible status helper used by main.py health checks."""
    status = get_model_status()
    shadow = get_shadow_model_status()
    base = {"torch_available": TORCH_AVAILABLE, "shadow_v2": shadow}
    if not TORCH_AVAILABLE:
        return {
            **base,
            "loaded": False,
            "path": status.get("path"),
            "error": SERVER_UNAVAILABLE_MESSAGE,
        }
    if not status["loaded"]:
        error = MODEL_UNAVAILABLE_MESSAGE
        return {
            **base,
            "loaded": False,
            "path": status.get("path"),
            "error": error,
        }
    try:
        bundle = load_engine()
        if bundle is None:
            return {
                **base,
                "loaded": False,
                "path": status.get("path"),
                "error": MODEL_UNAVAILABLE_MESSAGE,
            }
        return {
            **base,
            "loaded": True,
            "path": status["path"],
            "classes": bundle["class_names"],
            "device": str(bundle["device"]),
        }
    except ModelLoadError as e:
        return {
            **base,
            "loaded": False,
            "path": status.get("path"),
            "error": str(e),
        }
