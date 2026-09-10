import XCTest
@testable import CaucoHostCore

@MainActor final class NativeHandsFreeCoordinatorTests: XCTestCase {
  func testCloseIntentDecisionNormalizesSpanishAndEnglishVariants() {
    let closeRequests = ["¡Cierra el chat!", "termina la conversación", "para de escuchar", "close voice chat", "Stop the voice chat."]
    let confirmations = ["Sí, cierra", "CIÉRRALO", "confirmo", "yes close it", "Close it!"]
    let declines = ["No", "continúa", "Tengo más preguntas", "continue", "I have more questions"]
    for value in closeRequests { XCTAssertEqual(NativeHandsFreeCoordinator.closeIntentDecision(value), .asksToClose) }
    for value in confirmations { XCTAssertEqual(NativeHandsFreeCoordinator.closeIntentDecision(value), .confirmsClose) }
    for value in declines { XCTAssertEqual(NativeHandsFreeCoordinator.closeIntentDecision(value), .declinesClose) }
    XCTAssertEqual(NativeHandsFreeCoordinator.closeIntentDecision("¿qué tiempo hará mañana?"), .none)
  }

  func testCloseConfirmationClosesOnlyAfterExplicitSpanishOrEnglishConfirmation() async {
    for (request, confirmation) in [("cierra el chat", "sí"), ("close the voice chat", "yes")] {
      let f = Fixtures(); let c = f.coordinator(); c.startVoiceSession()
      f.transcriber.emit(request); await Task.yield()
      XCTAssertEqual(c.state, .speaking); XCTAssertEqual(f.conversation.requests, 0)
      f.synthesizer.finish(); await Task.yield()
      XCTAssertEqual(c.state, .listening)
      f.transcriber.emit(confirmation); await Task.yield()
      XCTAssertEqual(c.state, .speaking); XCTAssertEqual(f.conversation.requests, 0)
      f.synthesizer.finish(); await Task.yield()
      XCTAssertEqual(c.state, .disabled); XCTAssertEqual(f.transcriber.stops, 1)
    }
  }

  func testCloseConfirmationDeclineKeepsSessionListeningWithoutCallingLLM() async {
    let f = Fixtures(); let c = f.coordinator(); c.startVoiceSession()
    f.transcriber.emit("stop listening"); await Task.yield(); f.synthesizer.finish(); await Task.yield()
    f.transcriber.emit("tengo más preguntas"); await Task.yield()
    XCTAssertEqual(c.state, .listening); XCTAssertEqual(f.conversation.requests, 0)
  }

  func testNewQuestionDuringCloseConfirmationCancelsCloseAndUsesConversation() async {
    let f = Fixtures(); let c = f.coordinator(); c.startVoiceSession()
    f.transcriber.emit("cierra el chat de voz"); await Task.yield(); f.synthesizer.finish(); await Task.yield()
    f.transcriber.emit("¿Qué tiempo hará mañana?"); await Task.yield()
    XCTAssertEqual(c.state, .thinking); XCTAssertEqual(f.conversation.requests, 1)
  }

  func testVoiceSessionStartsSTTWithoutStartingWakeListener() {
    let f = Fixtures(); let c = f.coordinator()
    c.startVoiceSession()
    XCTAssertEqual(f.wake.starts, 0)
    XCTAssertEqual(f.transcriber.starts, 1)
    XCTAssertEqual(c.state, .listening)
    c.endVoiceSession()
    XCTAssertEqual(f.wake.stops, 1)
    XCTAssertEqual(f.transcriber.stops, 1)
  }

  func testSelectedSpeechLocaleIsUsedForVoiceOutput() async {
    let f = Fixtures(); let c = f.coordinator(); c.setSpeechLocale(Locale(identifier: "es-ES")); c.startVoiceSession()
    f.transcriber.emit("hola"); await Task.yield(); f.conversation.succeed("respuesta"); await Task.yield()
    XCTAssertEqual(f.synthesizer.lastLocale?.identifier, "es-ES")
  }

  func testEnableAndWakeToThinkingUsesOneTurn() async throws {
    let f = Fixtures(); let c = f.coordinator()
    c.enable(locale: "en-US"); XCTAssertEqual(c.state, .waitingForWake); XCTAssertEqual(f.wake.starts, 1)
    f.wake.emit(); await Task.yield(); XCTAssertEqual(f.wake.stops, 1); XCTAssertEqual(f.presentation.shows, 1); XCTAssertEqual(f.transcriber.starts, 1)
    f.transcriber.emit("hello"); await Task.yield(); XCTAssertEqual(c.state, .thinking); XCTAssertEqual(f.conversation.requests, 1)
    f.transcriber.emit("duplicate"); await Task.yield(); XCTAssertEqual(f.conversation.requests, 1)
  }

  func testResponseThenTTSThenRearm() async {
    let f = Fixtures(); let c = f.coordinator(); c.enable(locale: "en-US"); f.wake.emit(); await Task.yield(); f.transcriber.emit("hello"); await Task.yield()
    XCTAssertEqual(f.synthesizer.starts, 0); f.conversation.succeed("answer"); await Task.yield(); XCTAssertEqual(f.synthesizer.starts, 1)
    XCTAssertEqual(f.wake.starts, 1); f.synthesizer.finish(); await Task.yield(); XCTAssertEqual(f.wake.starts, 2); XCTAssertEqual(c.state, .waitingForWake)
  }

  func testDisableInvalidatesStaleCallbacksAndCancelsAll() {
    let f = Fixtures(); let c = f.coordinator(); c.enable(locale: "en-US"); let stale = f.wake.callback!; c.disable()
    stale(WakeWordDetectedEvent(eventReference: "stale", phraseKey: "hola_cauco", detectedAt: Date(), confidence: nil))
    XCTAssertEqual(c.state, .disabled); XCTAssertEqual(f.presentation.shows, 0); XCTAssertEqual(f.transcriber.stops, 1); XCTAssertEqual(f.conversation.cancels, 1); XCTAssertEqual(f.synthesizer.stops, 1)
  }

  func testProviderFailureDoesNotRearm() async {
    let f = Fixtures(); let c = f.coordinator(); c.enable(locale: "en-US"); f.wake.emit(); await Task.yield(); f.transcriber.emit("hello"); await Task.yield(); f.conversation.fail(); await Task.yield()
    XCTAssertEqual(c.state, .error); XCTAssertEqual(f.wake.starts, 1)
  }
}

@MainActor private final class Fixtures {
  let wake = FakeWake(); let transcriber = FakeTranscriber(); let conversation = FakeConversation(); let synthesizer = FakeSynthesizer(); let presentation = FakePresentation()
  func coordinator() -> NativeHandsFreeCoordinator { NativeHandsFreeCoordinator(wake: wake, transcriber: transcriber, conversation: conversation, synthesizer: synthesizer, presentation: presentation) }
}
@MainActor private final class FakeWake: NativeWakeListener { var starts = 0; var stops = 0; var callback: ((WakeWordDetectedEvent) -> Void)?; func start(locale: String, onDetection: @escaping (WakeWordDetectedEvent) -> Void) throws { starts += 1; callback = onDetection }; func stop() { stops += 1; callback = nil }; func emit() { callback?(WakeWordDetectedEvent(eventReference: "e", phraseKey: "hola_cauco", detectedAt: Date(), confidence: nil)) } }
@MainActor private final class FakeTranscriber: SpeechTranscriber { var permissionState: SpeechPermissionState = .authorized; var onDeviceAvailable = true; var state: SpeechTranscriptionState = .idle; var starts = 0; var stops = 0; var callback: ((String) -> Void)?; func start(locale: Locale, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void) { starts += 1; callback = onTranscript; state = .listening }; func stop() { stops += 1; callback = nil; state = .stopped }; func emit(_ text: String) { callback?(text) } }
@MainActor private final class FakeConversation: ConversationResponding { var requests = 0; var cancels = 0; var completion: ((Result<String, Error>) -> Void)?; func respond(instruction: String, useReasoning: Bool, completion: @escaping (Result<String, Error>) -> Void) { requests += 1; self.completion = completion }; func cancel() { cancels += 1; completion = nil }; func succeed(_ text: String) { completion?(.success(text)); completion = nil }; func fail() { completion?(.failure(NSError(domain: "test", code: 1))); completion = nil } }
@MainActor private final class FakeSynthesizer: SpeechSynthesizer { var state: SpeechSynthesisState = .idle; var starts = 0; var stops = 0; var lastLocale: Locale?; var completion: (() -> Void)?; func speak(_ text: String, locale: Locale, onComplete: @escaping () -> Void, onError: @escaping (Error) -> Void) { starts += 1; lastLocale = locale; state = .speaking; completion = onComplete }; func stop() { stops += 1; completion = nil; state = .stopped }; func finish() { completion?(); completion = nil; state = .completed } }
@MainActor private final class FakePresentation: HandsFreePresentation { var shows = 0; func showConversation() { shows += 1 }; func updateHandsFree(state: NativeHandsFreeState, transcript: String?, response: String?) {} }
