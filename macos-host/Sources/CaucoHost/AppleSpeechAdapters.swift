import AVFoundation
import Speech
import CaucoHostCore

@MainActor final class AppleSpeechTranscriber: NSObject, CaucoHostCore.SpeechTranscriber {
  private var recognizer: SFSpeechRecognizer?
  private var audioEngine: AVAudioEngine?
  private var request: SFSpeechAudioBufferRecognitionRequest?
  private var task: SFSpeechRecognitionTask?
  private var latestTranscript = ""
  private var silenceTimer: Task<Void, Never>?
  private var utteranceTimer: Task<Void, Never>?
  private var generation = 0
  private(set) var state: SpeechTranscriptionState = .idle

  // A one-shot command must not depend on Speech deciding when an open-ended
  // macOS audio request has ended. The maximum also bounds no-speech sessions.
  private let silenceIntervalNanoseconds: UInt64 = 1_500_000_000
  private let maximumUtteranceNanoseconds: UInt64 = 15_000_000_000

  var permissionState: SpeechPermissionState {
    switch SFSpeechRecognizer.authorizationStatus() {
    case .authorized: return .authorized
    case .denied: return .denied
    case .restricted: return .restricted
    case .notDetermined: return .notDetermined
    @unknown default: return .unavailable
    }
  }

  var onDeviceAvailable: Bool { recognizer?.supportsOnDeviceRecognition ?? false }

  func start(locale: Locale, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void) {
    guard task == nil else { return }
    generation += 1
    let token = generation
    state = .requestingPermission
    SFSpeechRecognizer.requestAuthorization { [weak self] status in
      Task { @MainActor [weak self] in
        guard let self, self.generation == token else { return }
        guard status == .authorized else { self.state = .failed; onError(VoiceFoundationError.permissionDenied); return }
        guard AVCaptureDevice.authorizationStatus(for: .audio) != .denied else {
          self.state = .failed; onError(VoiceFoundationError.permissionDenied); return
        }
        if AVCaptureDevice.authorizationStatus(for: .audio) == .notDetermined {
          let granted = await AVCaptureDevice.requestAccess(for: .audio)
          guard granted else { self.state = .failed; onError(VoiceFoundationError.permissionDenied); return }
        }
        self.begin(locale: locale, token: token, onTranscript: onTranscript, onError: onError)
      }
    }
  }

  private func begin(locale: Locale, token: Int, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void) {
    guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.supportsOnDeviceRecognition else {
      state = .failed; onError(VoiceFoundationError.onDeviceUnavailable); return
    }
    let request = SFSpeechAudioBufferRecognitionRequest(); request.requiresOnDeviceRecognition = true
    request.shouldReportPartialResults = true
    let engine = AVAudioEngine(); let input = engine.inputNode
    input.installTap(onBus: 0, bufferSize: 1_024, format: input.inputFormat(forBus: 0)) { [weak request] buffer, _ in request?.append(buffer) }
    do { engine.prepare(); try engine.start() } catch { input.removeTap(onBus: 0); state = .failed; onError(error); return }
    self.recognizer = recognizer; self.audioEngine = engine; self.request = request; latestTranscript = ""; state = .listening
    task = recognizer.recognitionTask(with: request) { [weak self] result, error in
      Task { @MainActor [weak self] in
        guard let self, self.generation == token, self.task != nil else { return }
        if let result {
          let transcript = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
          if !transcript.isEmpty { self.latestTranscript = transcript; self.state = .transcribing; self.scheduleSilenceCompletion(token: token, onTranscript: onTranscript, onError: onError) }
          if result.isFinal { self.finishTranscript(token: token, onTranscript: onTranscript) }
        }
        if let error { self.finishError(token: token, error: error, onError: onError) }
      }
    }
    scheduleUtteranceTimeout(token: token, onTranscript: onTranscript, onError: onError)
  }

  func stop() { generation += 1; stopResources(); state = .stopped }

  private func scheduleSilenceCompletion(token: Int, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void) {
    silenceTimer?.cancel()
    silenceTimer = Task { [weak self] in
      try? await Task.sleep(nanoseconds: self?.silenceIntervalNanoseconds ?? 0)
      guard !Task.isCancelled else { return }
      await self?.finishAfterSilence(token: token, onTranscript: onTranscript, onError: onError)
    }
  }

  private func scheduleUtteranceTimeout(token: Int, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void) {
    utteranceTimer?.cancel()
    utteranceTimer = Task { [weak self] in
      try? await Task.sleep(nanoseconds: self?.maximumUtteranceNanoseconds ?? 0)
      guard !Task.isCancelled else { return }
      await self?.finishAfterTimeout(token: token, onTranscript: onTranscript, onError: onError)
    }
  }

  private func finishAfterSilence(token: Int, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void) {
    guard latestTranscript.isEmpty == false else { return }
    finishTranscript(token: token, onTranscript: onTranscript)
  }

  private func finishAfterTimeout(token: Int, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void) {
    if latestTranscript.isEmpty { finishError(token: token, error: VoiceFoundationError.noSpeechDetected, onError: onError) }
    else { finishTranscript(token: token, onTranscript: onTranscript) }
  }

  private func finishTranscript(token: Int, onTranscript: @escaping (String) -> Void) {
    guard generation == token, task != nil else { return }
    let transcript = latestTranscript
    generation += 1
    silenceTimer?.cancel(); utteranceTimer?.cancel()
    stopResources(); state = .completed
    guard !transcript.isEmpty else { return }
    onTranscript(transcript)
  }

  private func finishError(token: Int, error: Error, onError: @escaping (Error) -> Void) {
    guard generation == token, task != nil else { return }
    generation += 1
    silenceTimer?.cancel(); utteranceTimer?.cancel()
    stopResources(); state = .failed
    onError(error)
  }

  private func stopResources() {
    silenceTimer?.cancel(); utteranceTimer?.cancel(); silenceTimer = nil; utteranceTimer = nil
    audioEngine?.inputNode.removeTap(onBus: 0); audioEngine?.stop(); request?.endAudio(); task?.cancel()
    audioEngine = nil; request = nil; task = nil; recognizer = nil; latestTranscript = ""
  }
}

@MainActor final class AppleSpeechSynthesizer: NSObject, CaucoHostCore.SpeechSynthesizer, AVSpeechSynthesizerDelegate {
  private let synthesizer = AVSpeechSynthesizer(); private var generation = 0; private(set) var state: SpeechSynthesisState = .idle
  override init() { super.init(); synthesizer.delegate = self }
  func speak(_ text: String, locale: Locale, onComplete: @escaping () -> Void, onError: @escaping (Error) -> Void) {
    guard !text.isEmpty, !synthesizer.isSpeaking else { onError(VoiceFoundationError.busy); return }
    generation += 1; let token = generation; let utterance = AVSpeechUtterance(string: text); utterance.voice = AVSpeechSynthesisVoice(language: locale.identifier) ?? AVSpeechSynthesisVoice(language: "en-US"); state = .speaking
    synthesizer.speak(utterance); completion = { [weak self] in guard let self, self.generation == token else { return }; self.state = .completed; onComplete() }
  }
  func stop() { generation += 1; synthesizer.stopSpeaking(at: .immediate); state = .stopped; completion = nil }
  private var completion: (() -> Void)?
  func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) { completion?(); completion = nil }
}

public enum VoiceFoundationError: Error { case permissionDenied, onDeviceUnavailable, busy, noSpeechDetected }
