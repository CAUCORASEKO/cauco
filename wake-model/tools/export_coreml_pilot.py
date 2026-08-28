#!/usr/bin/env python3
"""Export the existing normalized temporal linear pilot to Core ML.

Developer-only exporter. Reads the dataset and uses TRAIN records only.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import coremltools as ct
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from train_temporal_acoustic import load_records  # noqa: E402


def main() -> None:
    root = Path("wake-model/dataset")
    out = Path("wake-model/local-output/coreml-pilot")
    out.mkdir(parents=True, exist_ok=True)
    records = load_records(root, True)
    train = [r for r in records if r["split"] == "train"]
    x = np.asarray([r["features"] for r in train], dtype=np.float32)
    y = np.asarray(["hola_cauco" if r["label"] == "target" else "non_target" for r in train])
    if x.shape[1] != 348:
        raise ValueError(f"expected 348 features, got {x.shape}")
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(C=1, max_iter=1000, random_state=0, multi_class="ovr")),
    ]).fit(x, y)
    spec = ct.converters.sklearn.convert(
        model,
        input_features=[("temporal_features", ct.models.datatypes.Array(348))],
        output_feature_names=["classLabel", "classProbability"],
    )
    mlmodel = out / "HolaCauco.mlmodel"
    spec = spec.get_spec()
    spec.description.metadata.author = "Cauco local pilot"
    spec.description.metadata.shortDescription = "Developer-only bounded Hola Cauco temporal pilot"
    spec.description.input[0].shortDescription = "Normalized temporal 348-dimensional features"
    spec.description.output[0].shortDescription = "Predicted bounded class label"
    spec.description.output[1].shortDescription = "Probability dictionary for bounded classes"
    ct.models.MLModel(spec).save(str(mlmodel))
    digest = hashlib.sha256(mlmodel.read_bytes()).hexdigest()
    manifest = {
        "model_name": "HolaCauco",
        "pilot_status": "feature-input-only; SoundAnalysis compatibility unverified",
        "feature_representation": "normalized temporal features",
        "feature_dimension": 348,
        "labels": ["hola_cauco", "non_target"],
        "training_sample_count": len(train),
        "training_split": "train",
        "coremltools_version": ct.__version__,
        "coreml_spec_version": spec.specificationVersion,
        "input_description": "temporal_features: float vector, shape 348",
        "output_description": "classLabel plus classProbability dictionary",
        "sha256": digest,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
