import CaucoHostCore
import Foundation

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
  init(presentation: ConversationPresentationModel, show: @escaping () -> Void) { self.presentation = presentation; self.show = show }
  func showConversation() { show() }
  func updateHandsFree(state: NativeHandsFreeState, transcript: String?, response: String?) {
    if let transcript { presentation.inputText = transcript }
    if let response { presentation.response = response }
    if state == .error { presentation.error = "Hands-free conversation is unavailable. No action was taken." }
  }
}

@MainActor
final class HostHandsFreeService {
  let coordinator: NativeHandsFreeCoordinator
  init(presentation: ConversationPresentationModel, conversation: ConversationResponding, showConversation: @escaping () -> Void,
       wake: NativeWakeListener? = nil, transcriber: SpeechTranscriber? = nil,
       synthesizer: SpeechSynthesizer? = nil, handsFreePresentation: HandsFreePresentation? = nil) {
    let hostPresentation = handsFreePresentation ?? HostHandsFreePresentation(presentation: presentation, show: showConversation)
    coordinator = NativeHandsFreeCoordinator(
      wake: wake ?? NativeWakeListenerAdapter(), transcriber: transcriber ?? AppleSpeechTranscriber(), conversation: conversation,
      synthesizer: synthesizer ?? AppleSpeechSynthesizer(), presentation: hostPresentation)
  }
  func enable(locale: String = "en-US") { coordinator.enable(locale: locale) }
  func disable() { coordinator.disable() }
  func shutdown() { coordinator.shutdown() }
}
