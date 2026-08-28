# Native wake-word pilot

This is an experimental, local-only macOS pilot for the `hola_cauco` phrase
(“Hola Cauco”). It is not production-authoritative and does not claim wake-word
quality.

The pilot path is `wakeword.start` → AVAudioEngine input tap → bounded in-memory
mono PCM → Swift 348D temporal features → direct Core ML `MLModel` prediction
→ bounded `wakeword.detected`. SoundAnalysis is not used by this feature-input
pilot classifier.
Audio is analyzed in memory only; PCM, scores, and model internals never leave
the native detector. No audio is written to disk or sent over the network.

Microphone status is inspected without prompting. Permission is requested only
after an explicit `wakeword.start` request. Denied/restricted permission,
missing or invalid model, unsupported audio, analyzer failure, and engine
failure fail closed.

The lifecycle is one-shot: three consecutive observations of the fixed pilot
label `hola_cauco` at confidence `0.85` stop the engine before emitting one
bounded event. Detection invalidates stale callbacks and remains inactive until
the user explicitly enables it again. `wakeword.stop` and host shutdown are
idempotent and stop capture.

The expected local model artifact is `WakeWord/HolaCauco.mlmodelc` in the host
bundle. The model is experimental and accepts engineered features rather than
raw audio; production accuracy is not claimed. Audio, features, and
probabilities remain local to the native detector and are not persisted or
exposed. A future raw-audio Core ML model may use SoundAnalysis.

To enable locally, place only a verified compatible pilot model in that bundle,
launch the host, inspect `wakeword.status`, and explicitly invoke
`wakeword.start` with `phrase_key=hola_cauco` and the supported locale. Disable
with `wakeword.stop`. No automatic re-arm or continuous conversation loop is
implemented.
