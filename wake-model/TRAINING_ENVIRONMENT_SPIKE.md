# Hola Cauco training-environment compatibility spike

Date: 2026-08-28. This is a read-only readiness report. No environment,
package, dataset, model, or production detector was changed.

## 1. Local Python runtimes

| Runtime | Path | Version | Relevant packages observed |
|---|---|---|---|
| Homebrew Python | `/opt/homebrew/bin/python3` | 3.14.6 | none of the requested ML packages |
| Homebrew Python 3.11 | `/opt/homebrew/bin/python3.11` → `/opt/homebrew/opt/python@3.11/bin/python3.11` | 3.11.15 | NumPy and SciPy present; no scikit-learn/librosa/torch/coremltools |
| Homebrew Python 3.12 | `/opt/homebrew/bin/python3.12` | 3.12.13 | none of the requested ML packages |
| Homebrew Python 3.14 | `/opt/homebrew/bin/python3.14` | 3.14.6 | none of the requested ML packages |
| system/framework Python 3.11 | `/usr/local/bin/python3.11` | 3.11.9 | NumPy, SciPy, scikit-learn present; no librosa/torch/coremltools |
| Cauco main venv | `.venv/bin/python` | 3.14.6 | intentionally dependency-light |

`python3.13` was not found. `pyenv` was not found. `uv` was found at
`/opt/homebrew/bin/uv`, version `0.11.26`; it was not used to create an
environment. The Homebrew inspection attempted to consult its local/API
metadata but was blocked by the sandbox cache permission; no installation or
download was performed.

## 2. Local toolchain

- Homebrew: `/opt/homebrew/bin/brew`, 6.0.17
- Xcode: 26.5, build 17F42
- Swift: `/usr/bin/swift`, driver 1.148.6, Apple Swift 6.3.2
- `xcrun`: `/usr/bin/xcrun`
- macOS SDK: `/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk`
- Core ML compiler: `/Applications/Xcode.app/Contents/Developer/usr/bin/coremlc`
- No macOS Create ML application or macOS CreateML framework was found in the
  inspected Xcode installation. CreateML frameworks were visible in other
  platform SDKs, which does not establish macOS training availability.

## 3. Package compatibility matrix

| Package | Local status | Python 3.14 conclusion | Apple Silicon/macOS conclusion |
|---|---|---|---|
| numpy | absent in Cauco venv; present in 3.11 installs | UNKNOWN without package metadata/install | likely practical, but not proven for this exact environment |
| scipy | absent in Cauco venv; present in 3.11 installs | UNKNOWN | likely practical on 3.11, unproven on 3.14 |
| scikit-learn | present only in `/usr/local/bin/python3.11` | UNKNOWN | usable candidate on Intel-oriented 3.11 install; not validated for ARM stack |
| librosa | not installed | UNKNOWN | not assessed locally |
| torch | not installed | UNKNOWN | not assessed locally |
| torchaudio | not installed | UNKNOWN | not assessed locally |
| tensorflow | not installed | UNKNOWN | not assessed locally |
| coremltools | not installed | UNKNOWN | not assessed locally |

No network access or package installation was used to resolve unknowns. Python
3.11 is the strongest compatibility candidate because the local ecosystem
already contains NumPy/SciPy and scikit-learn in separate 3.11 installations.
That observation does not prove that a future isolated ARM environment will
have compatible wheels. `coremltools` compatibility and Core ML export support
must be verified after environment creation.

## 4. SoundAnalysis/Core ML constraints proven locally

The macOS 26.5 SDK headers prove:

- `SoundAnalysis` and `CoreML` are SDK frameworks.
- `SNClassifySoundRequest` supports
  `initWithMLModel:MLModel:error:` in
  `SoundAnalysis.framework/Versions/A/Headers/SNClassifySoundRequest.h`.
- It also supports `initWithClassifierIdentifier:error:` from macOS 12.
- `SNClassifierIdentifierVersion1` is declared in `SNTypes.h`.
- `SNAudioStreamAnalyzer` accepts PCM through
  `analyzeAudioBuffer:atAudioFramePosition:`.
- The analyzer may re-block variable buffers and perform sample-rate
  conversion, according to `SNClassifySoundRequest.h`.
- Analyzer calls may block for backpressure and are not safe from a realtime
  audio context, according to `SNAnalyzer.h`; an audio tap/lower-priority
  queue is the intended integration boundary.

The custom model requirement is also explicit in the header: the model must
accept audio and output a classification dictionary of category probabilities.

Proven locally: a custom `MLModel` can be passed to SoundAnalysis.
Likely but unproven: a model exported by a particular Python framework will
meet SoundAnalysis audio-input/output requirements.
Requires future validation: actual model input feature names/types, output
shape, sample-rate contract, model metadata, `coremltools` conversion fidelity,
and runtime behavior on macOS 13.

An arbitrary scikit-learn classifier is not automatically SoundAnalysis
compatible. It must be converted into a Core ML audio model with the required
audio input and probability dictionary output, then tested through
`SNClassifySoundRequest(mlModel:error:)`.

## 5. Training-strategy comparison

| Direction | Fit for current pilot | Core ML path | Assessment |
|---|---|---|---|
| Handcrafted log-mel/MFCC + classical classifier | explainable, but tiny/noisy data and feature engineering risk | possible only with a separate compatible model wrapper | useful diagnostic, not preferred runtime path |
| Small neural audio classifier | best chance to learn phrase-specific acoustics and export audio input | plausible through a verified conversion path | recommended, after environment validation |
| Transfer learning | potentially strong but data/model-download and licensing complexity | possible but high integration burden | defer until a clean local baseline exists |
| Create ML Sound Classification | conceptually aligned with SoundAnalysis | potentially direct Apple workflow | not locally established: no macOS Create ML tooling found |
| Existing nearest-centroid DFT baseline | deterministic | not a SoundAnalysis model | diagnostic only; its 0% target recall rules out activation use |

The tiny pilot is suitable for proving the pipeline, not for any meaningful
false-positive safety claim. A small supervised neural classifier using fixed
log-mel features is the best next technical direction, provided the feature
and export stack is proven in an isolated environment. It should initially
optimize hard-negative rejection, not overall accuracy.

## 6. Recommended isolated environment

Create later at `wake-model/.venv` using `/opt/homebrew/bin/python3.11` and
`uv` or standard `venv`; this must remain separate from `.venv` used by Cauco.
The initial dependency set should be minimal and explicitly pinned after
offline/approved installation planning:

1. NumPy
2. SciPy only if needed for signal processing
3. scikit-learn for a diagnostic classifier
4. one deliberately selected audio-feature package only if standard-library
   or NumPy/SciPy feature extraction proves insufficient
5. `coremltools` only as an optional export dependency

Do not install PyTorch, TensorFlow, torchaudio, or transfer-learning assets in
the first environment. Gitignore `wake-model/.venv/`, caches, model binaries,
and local outputs. Keep the existing main Cauco environment untouched.

## 7. Dataset readiness

Current metadata is structurally valid and contains:

| Split | target | hard_negative_speech | background | Total |
|---|---:|---:|---:|---:|
| train | 12 | 8 | 5 | 25 |
| validation | 3 | 3 | 5 | 11 |
| test | 0 | 0 | 0 | 0 |

It is sufficient for a proof-of-pipeline and feature-shape experiment. It is
not sufficient for a meaningful activation or false-positive claim: the
validation set is very small, the class balance is uneven, and there is no
held-out test set. Do not reuse validation as test.

The most valuable next data is speaker-disjoint target speech, substantially
more hard-negative Spanish speech, and background from unseen rooms/devices.
Introduce test recordings only after the split is deliberately defined and
the test speakers/environments/source groups are held out from development.

## 8. Recommended next step

Create `wake-model/.venv` with Python 3.11 using `uv` or `venv`, then perform a
small compatibility experiment with pinned NumPy/SciPy/scikit-learn and an
offline log-mel extractor. The experiment should consume train/validation
only, preserve the current test-empty state, and record feature dimensions,
per-class validation results, and hard-negative false positives. Core ML export
should be a separate follow-up after a model’s audio input/output contract is
verified.

## 9. Unknowns requiring future validation

- exact installable versions and wheel availability for Apple Silicon Python
  3.11;
- `coremltools` support for the selected Python version and model framework;
- whether the chosen model converter emits an audio-input model accepted by
  SoundAnalysis without custom preprocessing;
- exact Core ML input/output feature descriptions and probability labels;
- Create ML availability/licensing/workflow outside the inspected Xcode SDK;
- runtime latency, CPU, memory, energy, and compute-unit behavior on Apple
  Silicon and Intel Macs;
- performance on speaker- and environment-disjoint test data;
- the production threshold and temporal smoothing policy.

## Evidence and commands

Files/interfaces inspected included `macos-host/Package.swift`, the local
dataset metadata through `wake_model.py`, Xcode’s
`SNClassifySoundRequest.h`, `SNAnalyzer.h`, `SNTypes.h`, AVFAudio headers,
Core ML `MLModelConfiguration.h`, Xcode’s `coremlc`, and the main venv/runtime
configuration.

Commands included `command -v`, `--version`, `xcodebuild -version`,
`xcrun --sdk macosx --show-sdk-path`, read-only `find`/`rg` over SDK framework
headers/modules, package import/spec checks, and the existing dataset
validation command. No package installation or environment creation occurred.

Final status:

- Files changed: `wake-model/TRAINING_ENVIRONMENT_SPIKE.md` only.
- No packages installed.
- No virtual environment created.
- No dataset or metadata modified.
- No production Cauco code modified.
- No microphone, network dataset, cloud API, model download, or training run
  was used.
- No commit or push was performed.
