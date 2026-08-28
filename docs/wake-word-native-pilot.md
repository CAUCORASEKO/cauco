# Native wake-word pilot

This is an experimental, local-only macOS pilot for the `hola_cauco` phrase
(“Hola Cauco”). It is not production-authoritative and does not claim wake-word
quality.

The path is `wakeword.start` → AVAudioEngine input tap → SNAudioStreamAnalyzer
with a bundled Core ML `SNClassifySoundRequest` → bounded `wakeword.detected`.
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
bundle. No compatible artifact is currently bundled, so the runtime remains
unavailable until one is deliberately produced and verified with
`SNClassifySoundRequest`.

To enable locally, place only a verified compatible pilot model in that bundle,
launch the host, inspect `wakeword.status`, and explicitly invoke
`wakeword.start` with `phrase_key=hola_cauco` and the supported locale. Disable
with `wakeword.stop`. No automatic re-arm or continuous conversation loop is
implemented.
