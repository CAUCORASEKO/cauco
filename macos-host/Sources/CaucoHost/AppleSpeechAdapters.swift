import AVFoundation
import Speech
import CaucoHostCore

@MainActor final class AppleSpeechTranscriber: NSObject, CaucoHostCore.SpeechTranscriber {
  private var recognizer: SFSpeechRecognizer?
  private var audioEngine: AVAudioEngine?
  private var request: SFSpeechAudioBufferRecognitionRequest?
  private var task: SFSpeechRecognitionTask?
  private var generation = 0
  private(set) var state: SpeechTranscriptionState = .idle

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
    let engine = AVAudioEngine(); let input = engine.inputNode
    input.installTap(onBus: 0, bufferSize: 1_024, format: input.inputFormat(forBus: 0)) { [weak request] buffer, _ in request?.append(buffer) }
    do { engine.prepare(); try engine.start() } catch { input.removeTap(onBus: 0); state = .failed; onError(error); return }
    self.recognizer = recognizer; self.audioEngine = engine; self.request = request; state = .listening
    task = recognizer.recognitionTask(with: request) { [weak self] result, error in
      Task { @MainActor [weak self] in
        guard let self, self.generation == token, self.task != nil else { return }
        if let result { self.state = result.isFinal ? .completed : .transcribing; if result.isFinal { onTranscript(result.bestTranscription.formattedString); self.stopResources() } }
        if let error { self.state = .failed; self.stopResources(); onError(error) }
      }
    }
  }

  func stop() { generation += 1; stopResources(); state = .stopped }
  private func stopResources() { audioEngine?.inputNode.removeTap(onBus: 0); audioEngine?.stop(); request?.endAudio(); task?.cancel(); audioEngine = nil; request = nil; task = nil; recognizer = nil }
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

public enum VoiceFoundationError: Error { case permissionDenied, onDeviceUnavailable, busy }
