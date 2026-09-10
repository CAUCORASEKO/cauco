import CaucoHostCore
import Foundation
import Combine

enum HostSpeechLanguage: String, CaseIterable, Identifiable {
  case spanish = "es-ES", english = "en-US", finnish = "fi-FI"
  var id: String { rawValue }
  var title: String { switch self { case .spanish: return "Español"; case .english: return "English"; case .finnish: return "Suomi" } }
}

struct VoiceActivationRuntimeStatus: Equatable {
  let title: String
  let detail: String
  let symbolName: String
  let tone: VoiceActivationStatusTone

  static func forState(_ state: NativeHandsFreeState) -> Self {
    switch state {
    case .disabled: return .init(title: "Off", detail: "Voice activation is disabled.", symbolName: "circle", tone: .neutral)
    case .waitingForWake: return .init(title: "Listening", detail: "Waiting for \"Hola Cauco\"", symbolName: "mic", tone: .active)
    case .wakeDetected, .requestingSpeechPermission: return .init(title: "Activating", detail: "Wake phrase detected.", symbolName: "waveform", tone: .active)
    case .listening, .transcribing: return .init(title: "Listening to you", detail: "Speech recognition is active.", symbolName: "mic.fill", tone: .active)
    case .thinking: return .init(title: "Thinking", detail: "Preparing a response.", symbolName: "sparkles", tone: .active)
    case .speaking: return .init(title: "Speaking", detail: "Cauco is responding.", symbolName: "speaker.wave.2.fill", tone: .active)
    case .confirmingClose: return .init(title: "Confirming", detail: "Do you want to close the voice chat or ask more questions?", symbolName: "questionmark.bubble", tone: .active)
    case .rearming: return .init(title: "Rearming", detail: "Preparing wake listening.", symbolName: "arrow.clockwise", tone: .active)
    case .error: return .init(title: "Error", detail: "Wake listening stopped because of an error.", symbolName: "exclamationmark.triangle.fill", tone: .error)
    }
  }
}

enum VoiceActivationStatusTone { case neutral, active, error }

private let wakeListeningPreferenceKey = "cauco.voiceActivation.enabled"
private let speechLanguagePreferenceKey = "cauco.speechLanguage"

@MainActor
final class NativeWakeListenerAdapter: NativeWakeListener {
  private let detector: SoundAnalysisWakeWordDetectorGateway
  init(detector: SoundAnalysisWakeWordDetectorGateway = SoundAnalysisWakeWordDetectorGateway()) { self.detector = detector }
  func start(locale: String, onDetection: @escaping (WakeWordDetectedEvent) -> Void) throws {
    try detector.start(configuration: WakeWordDetectorConfiguration(phraseKey: "hola_cauco", locale: locale)) { signal in
      onDetection(WakeWordDetectedEvent(eventReference: "local-wake", phraseKey: "hola_cauco", detectedAt: Date(), confidence: signal.confidence))
    }
  }
  func stop() { detector.stop() }
}

@MainActor
final class HostHandsFreePresentation: HandsFreePresentation {
  private let show: () -> Void
  private let presentation: ConversationPresentationModel
  private let stateChanged: (NativeHandsFreeState) -> Void
  init(presentation: ConversationPresentationModel, show: @escaping () -> Void, stateChanged: @escaping (NativeHandsFreeState) -> Void = { _ in }) { self.presentation = presentation; self.show = show; self.stateChanged = stateChanged }
  func showConversation() { show() }
  func updateHandsFree(state: NativeHandsFreeState, transcript: String?, response: String?) {
    stateChanged(state)
    if let transcript { presentation.inputText = transcript }
    if let response { presentation.response = response }
    if state == .error { presentation.error = "Hands-free conversation is unavailable. No action was taken." }
  }
}

@MainActor
final class HostHandsFreeService: ObservableObject {
  let coordinator: NativeHandsFreeCoordinator
  @Published private(set) var state: NativeHandsFreeState = .disabled
  @Published private(set) var isEnabled = false
  var isWakeListeningEnabled: Bool { coordinator.wakeListeningEnabled }
  @Published private(set) var speechLanguage: HostSpeechLanguage
  init(presentation: ConversationPresentationModel, conversation: ConversationResponding, showConversation: @escaping () -> Void,
       wake: NativeWakeListener? = nil, transcriber: SpeechTranscriber? = nil,
       synthesizer: SpeechSynthesizer? = nil, handsFreePresentation: HandsFreePresentation? = nil) {
    let sink = HandsFreeStateSink()
    let hostPresentation = handsFreePresentation ?? HostHandsFreePresentation(presentation: presentation, show: showConversation, stateChanged: { state in sink.owner?.state = state })
    coordinator = NativeHandsFreeCoordinator(
      wake: wake ?? NativeWakeListenerAdapter(), transcriber: transcriber ?? AppleSpeechTranscriber(), conversation: conversation,
      synthesizer: synthesizer ?? AppleSpeechSynthesizer(), presentation: hostPresentation)
    speechLanguage = HostSpeechLanguage(rawValue: UserDefaults.standard.string(forKey: speechLanguagePreferenceKey) ?? "") ?? .spanish
    coordinator.setSpeechLocale(Locale(identifier: speechLanguage.rawValue))
    sink.owner = self
  }
  func restorePersistedWakeListening(locale: String = "en-US") {
    guard UserDefaults.standard.bool(forKey: wakeListeningPreferenceKey) else { refresh(); return }
    coordinator.enableWakeListening(locale: locale); refresh()
  }
  func enableWakeListening(locale: String = "en-US") { UserDefaults.standard.set(true, forKey: wakeListeningPreferenceKey); coordinator.enableWakeListening(locale: locale); refresh() }
  func disableWakeListening() { UserDefaults.standard.set(false, forKey: wakeListeningPreferenceKey); coordinator.disableWakeListening(); refresh() }
  func startVoiceSession() { coordinator.startVoiceSession(); refresh() }
  func endVoiceSession() { coordinator.endVoiceSession(); refresh() }
  func setSpeechLanguage(_ language: HostSpeechLanguage) { speechLanguage = language; UserDefaults.standard.set(language.rawValue, forKey: speechLanguagePreferenceKey); coordinator.setSpeechLocale(Locale(identifier: language.rawValue)) }
  func enable(locale: String = "en-US") { enableWakeListening(locale: locale) }
  func disable() { disableWakeListening() }
  func shutdown() { coordinator.shutdown(); refresh() }
  private func refresh() { isEnabled = coordinator.wakeListeningEnabled; state = coordinator.state; objectWillChange.send() }
}

@MainActor private final class HandsFreeStateSink {
  weak var owner: HostHandsFreeService?
}
