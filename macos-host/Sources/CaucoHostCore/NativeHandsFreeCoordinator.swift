import Foundation
import OSLog

@MainActor public final class NativeHandsFreeCoordinator: NativeHandsFreeCoordinating {
  private static let diagnosticLogger = Logger(subsystem: "com.cauco.host", category: "hands-free-runtime")
  public private(set) var state: NativeHandsFreeState = .disabled
  /// Persistent intent to return to wake listening after a voice session.
  public private(set) var wakeListeningEnabled = false
  /// Whether the physical wake detector currently owns the microphone.
  public private(set) var wakeListenerArmed = false
  public private(set) var isVoiceSessionActive = false
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

  public enum CloseIntentDecision: Equatable, Sendable { case none, asksToClose }

  public static func closeIntentDecision(_ text: String) -> CloseIntentDecision {
    let value = normalizedVoiceIntent(text)
    let close = [
      "apaga el chat de voz", "apaga chat de voz", "cerrar el chat de voz", "cerrar chat de voz",
      "cierra el chat de voz", "cierra chat de voz", "termina el chat de voz", "termina chat de voz",
      "close the voice chat", "close voice chat", "end the voice chat", "stop the voice chat",
    ]
    return close.contains(where: { value.contains($0) }) ? .asksToClose : .none
  }

  private static func normalizedVoiceIntent(_ text: String) -> String {
    let folded = text.lowercased().folding(options: .diacriticInsensitive, locale: .current)
    let separators = CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters).union(.symbols)
    return folded.components(separatedBy: separators).filter { !$0.isEmpty }.joined(separator: " ")
  }

  public init(wake: NativeWakeListener, transcriber: SpeechTranscriber,
              conversation: ConversationResponding, synthesizer: SpeechSynthesizer,
              presentation: HandsFreePresentation) {
    self.wake = wake; self.transcriber = transcriber; self.conversation = conversation
    self.synthesizer = synthesizer; self.presentation = presentation
  }

  public func enableWakeListening(locale: String) {
    wakeListeningEnabled = true; self.locale = locale
    guard !isVoiceSessionActive else { return }
    startWake()
  }

  public func startVoiceSession() {
    guard !isVoiceSessionActive else { return }
    // A voice session always owns the microphone; stop wake before STT starts.
    stopWake()
    if state != .disabled { transition(to: .disabled) }
    isVoiceSessionActive = true; locale = speechLocale.identifier
    generation.advance(); turnActive = true; transcriptAccepted = false
    transition(to: .requestingSpeechPermission)
    startSpeechListening(token: generation.current())
  }

  public func endVoiceSession() {
    guard isVoiceSessionActive else { return }
    isVoiceSessionActive = false; generation.advance(); turnActive = false; transcriptAccepted = false
    let closeToken = generation.current()
    cancelVoiceComponents()
    if state != .disabled { transition(to: .disabled) }
    scheduleWakeRearm(afterClosingToken: closeToken)
  }

  public func setSpeechLocale(_ locale: Locale) { speechLocale = locale; self.locale = locale.identifier }

  public func disableWakeListening() {
    guard wakeListeningEnabled || isVoiceSessionActive || state != .disabled else { return }
    wakeListeningEnabled = false; isVoiceSessionActive = false; generation.advance(); turnActive = false; transcriptAccepted = false
    cancelComponents()
    if state != .disabled { transition(to: .disabled) }
  }

  public func shutdown() {
    wakeListeningEnabled = false; isVoiceSessionActive = false; generation.advance(); turnActive = false; transcriptAccepted = false
    cancelComponents(); state = .disabled
  }

  private func startWake() {
    guard wakeListeningEnabled, !isVoiceSessionActive, !turnActive, !wakeListenerArmed else { return }
    let token = generation.current()
    do {
      try wake.start(locale: locale) { [weak self] event in
        Task { @MainActor [weak self] in self?.wakeDetected(event, token: token) }
      }
      wakeListenerArmed = true
      transition(to: .waitingForWake)
    } catch { fail(token: token, origin: "wake.start", error: error) }
  }

  private func stopWake() {
    guard wakeListenerArmed else { return }
    wake.stop(); wakeListenerArmed = false
  }

  private func scheduleWakeRearm(afterClosingToken token: Int) {
    guard wakeListeningEnabled else { return }
    Task { @MainActor [weak self] in
      await Task.yield()
      guard let self,
            self.generation.isCurrent(token),
            self.wakeListeningEnabled,
            !self.isVoiceSessionActive,
            !self.wakeListenerArmed else { return }
      self.startWake()
    }
  }

  private func wakeDetected(_ event: WakeWordDetectedEvent, token: Int) {
    guard generation.isCurrent(token), wakeListeningEnabled, wakeListenerArmed,
          state == .waitingForWake, !turnActive, !isVoiceSessionActive else { return }
    Self.diagnosticLogger.info("hands_free_wake_accepted token=\(token, privacy: .public) event_reference=\(event.eventReference, privacy: .public)")
    stopWake()
    transition(to: .wakeDetected); presentation.showConversation()
    // The wake event enters the same session path as the manual button.
    startVoiceSession()
  }

  private func startSpeechListening(token: Int) {
    transition(to: .listening)
    transcriber.start(locale: speechLocale, onTranscript: { [weak self] text in
      Task { @MainActor [weak self] in self?.transcript(text, token: token) }
    }, onError: { [weak self] error in
      Task { @MainActor [weak self] in self?.speechError(error, token: token) }
    })
  }

  private func speechError(_ error: Error, token: Int) {
    guard generation.isCurrent(token) else { return }
    if case .noSpeechDetected = error as? VoiceFoundationError {
      Self.diagnosticLogger.debug("voice_session_idle_timeout token=\(token, privacy: .public) current_generation=\(self.generation.current(), privacy: .public) session_ended=true wake_rearm_requested=\(self.wakeListeningEnabled, privacy: .public)")
      endVoiceSession()
      return
    }
    fail(token: token, origin: "stt", error: error)
  }

  private func transcript(_ text: String, token: Int) {
    guard generation.isCurrent(token), turnActive, !transcriptAccepted else { return }
    let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !value.isEmpty else { fail(token: token, origin: "transcript.empty", reason: "empty_transcript"); return }
    transcriptAccepted = true
    if isVoiceSessionActive, Self.closeIntentDecision(value) == .asksToClose {
      // Reversible close: never confirm, speak, or call the backend.
      endVoiceSession()
      return
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
    case .failure(let error): fail(token: token, origin: "conversation.failure", error: error)
    case .success(let text):
      let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !value.isEmpty else { fail(token: token, origin: "conversation.empty", reason: "empty_response"); return }
      speak(value, token: token)
    }
  }

  private func speak(_ text: String, token: Int) {
    transition(to: .speaking); presentation.updateHandsFree(state: .speaking, transcript: nil, response: text)
    synthesizer.speak(text, locale: Locale(identifier: locale), onComplete: { [weak self] in
      Task { @MainActor [weak self] in
        guard let self, self.generation.isCurrent(token), self.isVoiceSessionActive else { return }
        self.transcriptAccepted = false; self.generation.advance()
        self.startSpeechListening(token: self.generation.current())
      }
    }, onError: { [weak self] error in
      Task { @MainActor [weak self] in self?.fail(token: token, origin: "tts", error: error) }
    })
  }

  public func enable(locale: String) { enableWakeListening(locale: locale) }
  public func disable() { disableWakeListening() }

  private func fail(token: Int, origin: String, error: Error? = nil, reason: String = "callback_error") {
    guard generation.isCurrent(token) else { return }
    let nsError = error.map { $0 as NSError }
    Self.diagnosticLogger.debug("hands_free_fail origin=\(origin, privacy: .public) token=\(token, privacy: .public) current_generation=\(self.generation.current(), privacy: .public) is_voice_session_active=\(self.isVoiceSessionActive, privacy: .public) reason=\(reason, privacy: .public) error_domain=\(nsError?.domain ?? "none", privacy: .public) error_code=\(nsError?.code ?? 0, privacy: .public)")
    generation.advance(); isVoiceSessionActive = false; turnActive = false; transcriptAccepted = false
    cancelComponents(); transition(to: .error)
  }

  private func cancelVoiceComponents() { transcriber.stop(); conversation.cancel(); synthesizer.stop() }
  private func cancelComponents() { stopWake(); cancelVoiceComponents() }

  private func transition(to next: NativeHandsFreeState) {
    guard state != next else { return }
    if NativeHandsFreeStateMachine.canTransition(from: state, to: next) {
      state = next; presentation.updateHandsFree(state: next, transcript: nil, response: nil)
    } else {
      state = .error; presentation.updateHandsFree(state: .error, transcript: nil, response: nil)
    }
  }
}
