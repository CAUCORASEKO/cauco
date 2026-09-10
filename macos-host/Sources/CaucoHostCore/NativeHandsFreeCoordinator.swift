import Foundation
import OSLog

@MainActor public final class NativeHandsFreeCoordinator: NativeHandsFreeCoordinating {
  private static let diagnosticLogger = Logger(subsystem: "com.cauco.host", category: "hands-free-runtime")
  public private(set) var state: NativeHandsFreeState = .disabled
  /// Whether the local wake listener is armed. This is separate from turnActive.
  public private(set) var wakeListeningEnabled = false
  public var handsFreeEnabled: Bool { wakeListeningEnabled }

  private let wake: NativeWakeListener
  private let transcriber: SpeechTranscriber
  private let conversation: ConversationResponding
  private let synthesizer: SpeechSynthesizer
  private let presentation: HandsFreePresentation
  private let generation = NativeHandsFreeGeneration()
  private var locale = "en-US"
  private var speechLocale = Locale(identifier: "es-ES")
  private var transcriptAccepted = false
  private var turnActive = false
  private var voiceSessionActive = false
  private var awaitingCloseConfirmation = false

  public enum CloseIntentDecision: Equatable, Sendable { case none, asksToClose, confirmsClose, declinesClose }

  public static func closeIntentDecision(_ text: String) -> CloseIntentDecision {
    let value = normalizedVoiceIntent(text)
    let close = ["cierra el chat", "cierra el chat de voz", "termina el chat", "termina la conversacion", "deja de escuchar", "para de escuchar", "close the voice chat", "close voice chat", "end the conversation", "stop listening", "stop the voice chat"]
    let confirms = ["si", "si cierra", "cierra", "cierralo", "confirm", "confirmo", "yes", "yes close it", "close it"]
    let declines = ["no", "continua", "sigue", "tengo mas preguntas", "mantente alerta", "no cierres", "continue", "keep listening", "i have more questions", "stay listening"]
    if confirms.contains(value) { return .confirmsClose }
    if declines.contains(value) { return .declinesClose }
    return close.contains(where: { value.contains($0) }) ? .asksToClose : .none
  }

  private static func normalizedVoiceIntent(_ text: String) -> String {
    let folded = text.lowercased().folding(options: .diacriticInsensitive, locale: .current)
    let separators = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters).union(.symbols)
    return folded.components(separatedBy: separators).filter { !$0.isEmpty }.joined(separator: " ")
  }

  public init(
    wake: NativeWakeListener,
    transcriber: SpeechTranscriber,
    conversation: ConversationResponding,
    synthesizer: SpeechSynthesizer,
    presentation: HandsFreePresentation
  ) {
    self.wake = wake
    self.transcriber = transcriber
    self.conversation = conversation
    self.synthesizer = synthesizer
    self.presentation = presentation
  }

  public func enableWakeListening(locale: String) {
    guard !wakeListeningEnabled else { return }
    wakeListeningEnabled = true; self.locale = locale; startWake()
  }
  public func startVoiceSession() {
    guard !voiceSessionActive else { return }
    voiceSessionActive = true; wakeListeningEnabled = false; awaitingCloseConfirmation = false
    locale = speechLocale.identifier
    generation.advance(); turnActive = true; transcriptAccepted = false
    transition(to: .requestingSpeechPermission)
    startSpeechListening(token: generation.current())
  }
  public func endVoiceSession() {
    guard voiceSessionActive || state != .disabled else { return }
    voiceSessionActive = false; wakeListeningEnabled = false; awaitingCloseConfirmation = false
    generation.advance(); turnActive = false; transcriptAccepted = false; cancelComponents(); transition(to: .disabled)
  }
  public func setSpeechLocale(_ locale: Locale) { speechLocale = locale; self.locale = locale.identifier }

  public func disableWakeListening() {
    guard wakeListeningEnabled || state != .disabled else { return }
    wakeListeningEnabled = false; voiceSessionActive = false; generation.advance(); cancelComponents(); turnActive = false; transcriptAccepted = false
    transition(to: .disabled)
  }

  public func shutdown() {
    wakeListeningEnabled = false; voiceSessionActive = false; generation.advance(); cancelComponents(); turnActive = false; transcriptAccepted = false
    state = .disabled
  }

  private func startWake() {
    guard wakeListeningEnabled, !turnActive else { return }
    let token = generation.current()
    do {
      try wake.start(locale: locale) { [weak self] event in
        Task { @MainActor [weak self] in self?.wakeDetected(event, token: token) }
      }
      transition(to: .waitingForWake)
    } catch { fail(token: token) }
  }

  private func wakeDetected(_ event: WakeWordDetectedEvent, token: Int) {
    guard generation.isCurrent(token), wakeListeningEnabled, state == .waitingForWake, !turnActive else { return }
    Self.diagnosticLogger.info("hands_free_wake_accepted token=\(token, privacy: .public) event_reference=\(event.eventReference, privacy: .public)")
    turnActive = true; transcriptAccepted = false; generation.advance()
    let turnToken = generation.current()
    // Stop is deliberately synchronous and precedes both presentation and microphone start.
    wake.stop()
    Self.diagnosticLogger.info("hands_free_wake_stop_completed token=\(turnToken, privacy: .public)")
    transition(to: .wakeDetected); presentation.showConversation()
    transition(to: .requestingSpeechPermission)
    Self.diagnosticLogger.info("hands_free_stt_start token=\(turnToken, privacy: .public)")
    transcriber.start(locale: speechLocale, onTranscript: { [weak self] text in
      Task { @MainActor [weak self] in self?.transcript(text, token: turnToken) }
    }, onError: { [weak self] error in
      Task { @MainActor [weak self] in self?.fail(token: turnToken) }
    })
    transition(to: .listening)
  }

  private func startSpeechListening(token: Int) {
    transition(to: .listening)
    transcriber.start(locale: speechLocale, onTranscript: { [weak self] text in
      Task { @MainActor [weak self] in self?.transcript(text, token: token) }
    }, onError: { [weak self] error in
      Task { @MainActor [weak self] in self?.fail(token: token) }
    })
  }

  private func transcript(_ text: String, token: Int) {
    guard generation.isCurrent(token), turnActive, !transcriptAccepted else { return }
    let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !value.isEmpty else { fail(token: token); return }
    transcriptAccepted = true
    if awaitingCloseConfirmation {
      switch Self.closeIntentDecision(value) {
      case .confirmsClose:
        awaitingCloseConfirmation = false; voiceSessionActive = false; transition(to: .confirmingClose)
        speak("De acuerdo. Cierro el chat de voz. Hasta luego.", token: token, finishSession: true)
      case .declinesClose:
        awaitingCloseConfirmation = false; transcriptAccepted = false; generation.advance()
        startSpeechListening(token: generation.current())
      case .asksToClose:
        // A repeated close request is still a request, not confirmation. Keep the
        // pending state and ask the same explicit question again.
        transcriptAccepted = false; transition(to: .confirmingClose)
        speak("¿Quieres cerrar el chat de voz o tienes más preguntas?", token: token)
      case .none:
        awaitingCloseConfirmation = false; transcriptAccepted = false
        transition(to: .transcribing); transition(to: .thinking)
        presentation.updateHandsFree(state: .thinking, transcript: value, response: nil)
        conversation.respond(instruction: value, useReasoning: true) { [weak self] result in
          Task { @MainActor [weak self] in self?.conversationResult(result, token: token) }
        }
      }
      return
    }
    switch Self.closeIntentDecision(value) {
    case .asksToClose:
      awaitingCloseConfirmation = true; transition(to: .confirmingClose)
      speak("¿Quieres cerrar el chat de voz o tienes más preguntas?", token: token)
      return
    case .confirmsClose, .declinesClose: break
    case .none: break
    }
    transition(to: .transcribing); transition(to: .thinking)
    presentation.updateHandsFree(state: .thinking, transcript: value, response: nil)
    conversation.respond(instruction: value, useReasoning: true) { [weak self] result in
      Task { @MainActor [weak self] in self?.conversationResult(result, token: token) }
    }
  }

  private func conversationResult(_ result: Result<String, Error>, token: Int) {
    guard generation.isCurrent(token), turnActive, state == .thinking else { return }
    switch result {
    case .failure: fail(token: token)
    case .success(let text):
      let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !value.isEmpty else { fail(token: token); return }
      speak(value, token: token)
    }
  }

  private func speak(_ text: String, token: Int, finishSession: Bool = false) {
    transition(to: .speaking); presentation.updateHandsFree(state: .speaking, transcript: nil, response: text)
    synthesizer.speak(text, locale: Locale(identifier: locale), onComplete: { [weak self] in
      Task { @MainActor [weak self] in
        guard let self, self.generation.isCurrent(token) else { return }
        if finishSession { self.endVoiceSession() }
        else if self.voiceSessionActive && self.awaitingCloseConfirmation { self.transcriptAccepted = false; self.generation.advance(); self.startSpeechListening(token: self.generation.current()) }
        else if self.voiceSessionActive { self.transcriptAccepted = false; self.generation.advance(); self.startSpeechListening(token: self.generation.current()) }
        else { self.speechFinished(token: token) }
      }
    }, onError: { [weak self] _ in
      Task { @MainActor [weak self] in self?.fail(token: token) }
    })
  }

  private func speechFinished(token: Int) {
    guard generation.isCurrent(token), turnActive, state == .speaking else { return }
    turnActive = false; transcriptAccepted = false
    guard wakeListeningEnabled else { transition(to: .disabled); return }
    transition(to: .rearming); generation.advance(); startWake()
  }

  // Compatibility aliases keep the existing native contract stable while the
  // product-facing meaning is now explicitly wake-listening.
  public func enable(locale: String) { enableWakeListening(locale: locale) }
  public func disable() { disableWakeListening() }

  private func fail(token: Int) {
    guard generation.isCurrent(token) else { return }
    generation.advance(); cancelComponents(); turnActive = false; transcriptAccepted = false
    transition(to: .error)
  }

  private func cancelComponents() {
    wake.stop(); transcriber.stop(); conversation.cancel(); synthesizer.stop()
  }

  private func transition(to next: NativeHandsFreeState) {
    guard state != next else { return }
    if NativeHandsFreeStateMachine.canTransition(from: state, to: next) { state = next; presentation.updateHandsFree(state: next, transcript: nil, response: nil) }
    else { state = .error; presentation.updateHandsFree(state: .error, transcript: nil, response: nil) }
  }
}
