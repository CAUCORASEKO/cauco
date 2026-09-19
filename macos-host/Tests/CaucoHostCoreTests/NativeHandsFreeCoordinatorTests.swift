import XCTest
@testable import CaucoHostCore

@MainActor final class NativeHandsFreeCoordinatorTests: XCTestCase {
  func testWakeArmsWithoutStartingConversationalSTT() {
    let f = Fixtures(); let c = f.coordinator()
    c.enableWakeListening(locale: "en-US")
    XCTAssertTrue(c.wakeListeningEnabled); XCTAssertTrue(c.wakeListenerArmed)
    XCTAssertFalse(c.isVoiceSessionActive); XCTAssertEqual(c.state, .waitingForWake)
    XCTAssertEqual(f.wake.starts, 1); XCTAssertEqual(f.transcriber.starts, 0)
  }

  func testWakeStopsBeforeStartingVoiceSessionSTT() async {
    let f = Fixtures(); let c = f.coordinator(); c.enableWakeListening(locale: "en-US")
    f.wake.emit(); await Task.yield()
    XCTAssertEqual(f.events, ["wake.start", "wake.stop", "presentation", "stt.start"])
    XCTAssertTrue(c.isVoiceSessionActive); XCTAssertFalse(c.wakeListenerArmed)
    XCTAssertEqual(c.state, .listening); XCTAssertEqual(f.transcriber.starts, 1)
  }

  func testVoiceSessionContinuesFromTTSBackToSTTWithoutRearmingWake() async {
    let f = Fixtures(); let c = f.coordinator(); c.enableWakeListening(locale: "en-US"); f.wake.emit(); await Task.yield()
    f.transcriber.emit("hola"); await Task.yield(); f.conversation.succeed("respuesta"); await Task.yield()
    XCTAssertEqual(c.state, .speaking); XCTAssertEqual(f.wake.starts, 1)
    f.synthesizer.finish(); await Task.yield()
    XCTAssertTrue(c.isVoiceSessionActive); XCTAssertEqual(c.state, .listening)
    XCTAssertEqual(f.transcriber.starts, 2); XCTAssertEqual(f.wake.starts, 1)
  }

  func testCloseIntentClosesDirectlyWithoutTTSOrBackendAndRearmsWake() async {
    for phrase in ["Cerrar Chat de voz", "Cerrar el Chat de voz"] {
      let f = Fixtures(); let c = f.coordinator(); c.enableWakeListening(locale: "en-US"); f.wake.emit(); await Task.yield()
      f.transcriber.emit(phrase); await settle()
      XCTAssertFalse(c.isVoiceSessionActive); XCTAssertTrue(c.wakeListenerArmed)
      XCTAssertEqual(c.state, .waitingForWake); XCTAssertEqual(f.conversation.requests, 0)
      XCTAssertEqual(f.synthesizer.starts, 0); XCTAssertEqual(f.wake.starts, 2)
    }
  }

  func testSecondWakeStartsSecondVoiceSessionAfterDirectClose() async {
    let f = Fixtures(); let c = f.coordinator(); c.enableWakeListening(locale: "en-US")
    f.wake.emit(); await Task.yield(); f.transcriber.emit("Cerrar chat de voz"); await settle()
    XCTAssertEqual(c.state, .waitingForWake); XCTAssertFalse(c.isVoiceSessionActive)
    f.wake.emit(); await Task.yield()
    XCTAssertTrue(c.isVoiceSessionActive); XCTAssertEqual(c.state, .listening); XCTAssertEqual(f.transcriber.starts, 2)
  }

  func testManualCloseDefersWakeRearmUntilAfterClosingStack() async {
    let f = Fixtures(); let c = f.coordinator(); c.enableWakeListening(locale: "en-US")
    c.startVoiceSession()
    XCTAssertEqual(f.events, ["wake.start", "wake.stop", "stt.start"])
    XCTAssertTrue(c.isVoiceSessionActive); XCTAssertFalse(c.wakeListenerArmed)
    c.endVoiceSession()
    XCTAssertFalse(c.isVoiceSessionActive); XCTAssertFalse(c.wakeListenerArmed)
    XCTAssertEqual(c.state, .disabled); XCTAssertEqual(f.wake.starts, 1)
    await settle()
    XCTAssertTrue(c.wakeListenerArmed)
    XCTAssertEqual(c.state, .waitingForWake); XCTAssertEqual(f.wake.starts, 2)
  }

  func testPendingWakeRearmIsInvalidatedByANewManualVoiceSession() async {
    let f = Fixtures(); let c = f.coordinator(); c.enableWakeListening(locale: "en-US")
    c.startVoiceSession(); c.endVoiceSession()
    c.startVoiceSession()
    await settle()
    XCTAssertTrue(c.isVoiceSessionActive); XCTAssertFalse(c.wakeListenerArmed)
    XCTAssertEqual(c.state, .listening); XCTAssertEqual(f.wake.starts, 1)
  }

  func testManualCloseWithoutWakeEnabledStaysDisabled() async {
    let f = Fixtures(); let c = f.coordinator(); c.startVoiceSession(); c.endVoiceSession()
    await settle()
    XCTAssertFalse(c.wakeListeningEnabled); XCTAssertFalse(c.wakeListenerArmed)
    XCTAssertEqual(c.state, .disabled); XCTAssertEqual(f.wake.starts, 0)
  }

  func testNoSpeechDetectedEndsSessionAndRearmsWakeWithoutBackendOrTTS() async {
    let f = Fixtures(); let c = f.coordinator(); c.enableWakeListening(locale: "en-US")
    f.wake.emit(); await Task.yield()
    f.transcriber.emitError(VoiceFoundationError.noSpeechDetected)
    await settle()
    XCTAssertFalse(c.isVoiceSessionActive)
    XCTAssertEqual(c.state, .waitingForWake)
    XCTAssertTrue(c.wakeListenerArmed)
    XCTAssertEqual(f.wake.starts, 2)
    XCTAssertEqual(f.conversation.requests, 0)
    XCTAssertEqual(f.synthesizer.starts, 0)
  }

  func testStaleNoSpeechDetectedDoesNotAlterCurrentVoiceSession() async {
    let f = Fixtures(); let c = f.coordinator(); c.enableWakeListening(locale: "en-US")
    f.wake.emit(); await Task.yield()
    f.transcriber.emit("Cerrar chat de voz"); await settle()
    f.wake.emit(); await Task.yield()
    f.transcriber.emitError(VoiceFoundationError.noSpeechDetected, at: 0)
    await settle()
    XCTAssertTrue(c.isVoiceSessionActive)
    XCTAssertEqual(c.state, .listening)
    XCTAssertEqual(f.wake.starts, 2)
  }

  func testCurrentNonTimeoutSTTErrorRemainsFatal() async {
    let f = Fixtures(); let c = f.coordinator(); c.enableWakeListening(locale: "en-US")
    f.wake.emit(); await Task.yield()
    f.transcriber.emitError(NSError(domain: "speech-test", code: 42))
    await settle()
    XCTAssertFalse(c.isVoiceSessionActive)
    XCTAssertEqual(c.state, .error)
    XCTAssertEqual(f.wake.starts, 1)
  }

  func testTimeoutThenSecondWakeStartsANewVoiceSession() async {
    let f = Fixtures(); let c = f.coordinator(); c.enableWakeListening(locale: "en-US")
    f.wake.emit(); await Task.yield()
    f.transcriber.emitError(VoiceFoundationError.noSpeechDetected)
    await settle()
    f.wake.emit(); await Task.yield()
    XCTAssertTrue(c.isVoiceSessionActive)
    XCTAssertEqual(c.state, .listening)
    XCTAssertEqual(f.transcriber.starts, 2)
  }

  func testCloseIntentOnlyMatchesVoiceChatCommands() {
    for value in ["apaga el chat de voz", "cierra chat de voz", "termina el chat de voz"] {
      XCTAssertEqual(NativeHandsFreeCoordinator.closeIntentDecision(value), .asksToClose)
    }
    XCTAssertEqual(NativeHandsFreeCoordinator.closeIntentDecision("apaga la luz"), .none)
  }

  private func settle() async {
    for _ in 0..<3 { await Task.yield() }
  }
}

@MainActor private final class Fixtures {
  let wake = FakeWake(); let transcriber = FakeTranscriber(); let conversation = FakeConversation(); let synthesizer = FakeSynthesizer(); let presentation = FakePresentation(); var events: [String] = []
  init() { wake.events = { [weak self] in self?.events.append($0) }; transcriber.events = { [weak self] in self?.events.append($0) }; presentation.events = { [weak self] in self?.events.append($0) } }
  func coordinator() -> NativeHandsFreeCoordinator { NativeHandsFreeCoordinator(wake: wake, transcriber: transcriber, conversation: conversation, synthesizer: synthesizer, presentation: presentation) }
}
@MainActor private final class FakeWake: NativeWakeListener { var starts = 0; var callback: ((WakeWordDetectedEvent) -> Void)?; var events: ((String) -> Void)?; func start(locale: String, onDetection: @escaping (WakeWordDetectedEvent) -> Void) throws { starts += 1; events?("wake.start"); callback = onDetection }; func stop() { events?("wake.stop"); callback = nil }; func emit() { callback?(WakeWordDetectedEvent(eventReference: "e", phraseKey: "hola_cauco", detectedAt: Date(), confidence: nil)) } }
@MainActor private final class FakeTranscriber: SpeechTranscriber { var permissionState: SpeechPermissionState = .authorized; var onDeviceAvailable = true; var state: SpeechTranscriptionState = .idle; var starts = 0; var callback: ((String) -> Void)?; var errorCallbacks: [(Error) -> Void] = []; var events: ((String) -> Void)?; func start(locale: Locale, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void) { starts += 1; events?("stt.start"); callback = onTranscript; errorCallbacks.append(onError); state = .listening }; func stop() { callback = nil; state = .stopped }; func emit(_ text: String) { callback?(text) }; func emitError(_ error: Error, at index: Int? = nil) { errorCallbacks[index ?? (errorCallbacks.count - 1)](error) } }
@MainActor private final class FakeConversation: ConversationResponding { var requests = 0; var completion: ((Result<String, Error>) -> Void)?; func respond(instruction: String, useReasoning: Bool, completion: @escaping (Result<String, Error>) -> Void) { requests += 1; self.completion = completion }; func cancel() { completion = nil }; func succeed(_ text: String) { completion?(.success(text)); completion = nil } }
@MainActor private final class FakeSynthesizer: SpeechSynthesizer { var state: SpeechSynthesisState = .idle; var starts = 0; var completion: (() -> Void)?; func speak(_ text: String, locale: Locale, onComplete: @escaping () -> Void, onError: @escaping (Error) -> Void) { starts += 1; completion = onComplete; state = .speaking }; func stop() { completion = nil; state = .stopped }; func finish() { completion?(); completion = nil; state = .completed } }
@MainActor private final class FakePresentation: HandsFreePresentation { var events: ((String) -> Void)?; func showConversation() { events?("presentation") }; func updateHandsFree(state: NativeHandsFreeState, transcript: String?, response: String?) {} }
