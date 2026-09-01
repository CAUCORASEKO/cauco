import Foundation

@MainActor public final class NativeHandsFreeCoordinator: NativeHandsFreeCoordinating {
  public private(set) var state: NativeHandsFreeState = .disabled
  public private(set) var handsFreeEnabled = false

  private let wake: NativeWakeListener
  private let transcriber: SpeechTranscriber
  private let conversation: ConversationResponding
  private let synthesizer: SpeechSynthesizer
  private let presentation: HandsFreePresentation
  private let generation = NativeHandsFreeGeneration()
  private var locale = "en-US"
  private var transcriptAccepted = false
  private var turnActive = false

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

  public func enable(locale: String) {
    guard !handsFreeEnabled else { return }
    handsFreeEnabled = true; self.locale = locale; startWake()
  }

  public func disable() {
    guard handsFreeEnabled || state != .disabled else { return }
    handsFreeEnabled = false; generation.advance(); cancelComponents(); turnActive = false; transcriptAccepted = false
    transition(to: .disabled)
  }

  public func shutdown() {
    handsFreeEnabled = false; generation.advance(); cancelComponents(); turnActive = false; transcriptAccepted = false
    state = .disabled
  }

  private func startWake() {
    guard handsFreeEnabled, !turnActive else { return }
    let token = generation.current()
    do {
      try wake.start(locale: locale) { [weak self] event in
        Task { @MainActor [weak self] in self?.wakeDetected(event, token: token) }
      }
      transition(to: .waitingForWake)
    } catch { fail(token: token) }
  }

  private func wakeDetected(_ event: WakeWordDetectedEvent, token: Int) {
    guard generation.isCurrent(token), handsFreeEnabled, state == .waitingForWake, !turnActive else { return }
    turnActive = true; transcriptAccepted = false; generation.advance()
    let turnToken = generation.current()
    // Stop is deliberately synchronous and precedes both presentation and microphone start.
    wake.stop()
    transition(to: .wakeDetected); presentation.showConversation()
    transition(to: .requestingSpeechPermission)
    transcriber.start(locale: Locale(identifier: locale), onTranscript: { [weak self] text in
      Task { @MainActor [weak self] in self?.transcript(text, token: turnToken) }
    }, onError: { [weak self] error in
      Task { @MainActor [weak self] in self?.fail(token: turnToken) }
    })
    transition(to: .listening)
  }

  private func transcript(_ text: String, token: Int) {
    guard generation.isCurrent(token), turnActive, !transcriptAccepted else { return }
    let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !value.isEmpty else { fail(token: token); return }
    transcriptAccepted = true; transition(to: .transcribing); transition(to: .thinking)
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
      transition(to: .speaking); presentation.updateHandsFree(state: .speaking, transcript: nil, response: value)
      synthesizer.speak(value, locale: Locale(identifier: locale), onComplete: { [weak self] in
        Task { @MainActor [weak self] in self?.speechFinished(token: token) }
      }, onError: { [weak self] error in
        Task { @MainActor [weak self] in self?.fail(token: token) }
      })
    }
  }

  private func speechFinished(token: Int) {
    guard generation.isCurrent(token), turnActive, state == .speaking else { return }
    turnActive = false; transcriptAccepted = false
    guard handsFreeEnabled else { transition(to: .disabled); return }
    transition(to: .rearming); generation.advance(); startWake()
  }

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
