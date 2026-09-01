import CaucoHostCore
import Foundation
import Combine

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
  init(presentation: ConversationPresentationModel, conversation: ConversationResponding, showConversation: @escaping () -> Void,
       wake: NativeWakeListener? = nil, transcriber: SpeechTranscriber? = nil,
       synthesizer: SpeechSynthesizer? = nil, handsFreePresentation: HandsFreePresentation? = nil) {
    let sink = HandsFreeStateSink()
    let hostPresentation = handsFreePresentation ?? HostHandsFreePresentation(presentation: presentation, show: showConversation, stateChanged: { state in sink.owner?.state = state })
    coordinator = NativeHandsFreeCoordinator(
      wake: wake ?? NativeWakeListenerAdapter(), transcriber: transcriber ?? AppleSpeechTranscriber(), conversation: conversation,
      synthesizer: synthesizer ?? AppleSpeechSynthesizer(), presentation: hostPresentation)
    sink.owner = self
  }
  func enable(locale: String = "en-US") { coordinator.enable(locale: locale); isEnabled = coordinator.handsFreeEnabled; state = coordinator.state }
  func disable() { coordinator.disable(); isEnabled = coordinator.handsFreeEnabled; state = coordinator.state }
  func shutdown() { coordinator.shutdown(); isEnabled = coordinator.handsFreeEnabled; state = coordinator.state }
}

@MainActor private final class HandsFreeStateSink {
  weak var owner: HostHandsFreeService?
}
