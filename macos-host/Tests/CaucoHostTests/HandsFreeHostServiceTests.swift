import XCTest
@testable import CaucoHost
import CaucoHostCore

@MainActor
final class HandsFreeHostServiceTests: XCTestCase {
  func testVoiceActivationRuntimeStatusMappingIsIndependentOfPreference() {
    XCTAssertEqual(VoiceActivationRuntimeStatus.forState(.disabled).title, "Off")
    XCTAssertEqual(VoiceActivationRuntimeStatus.forState(.waitingForWake).detail, "Waiting for \"Hola Cauco\"")
    XCTAssertEqual(VoiceActivationRuntimeStatus.forState(.error).title, "Error")
    XCTAssertEqual(VoiceActivationRuntimeStatus.forState(.error).detail, "Wake listening stopped because of an error.")
  }

  func testServiceIsDisabledAndSideEffectFreeByDefault() {
    let fakes = Fixtures()
    let service = fakes.service()
    XCTAssertFalse(service.coordinator.handsFreeEnabled)
    XCTAssertEqual(service.coordinator.state, .disabled)
    XCTAssertEqual(fakes.wake.starts, 0); XCTAssertEqual(fakes.transcriber.starts, 0)
    XCTAssertEqual(fakes.synthesizer.speaks, 0); XCTAssertEqual(fakes.presentation.shows, 0)
  }

  func testWakePresentationAndSTTOrdering() async {
    let fakes = Fixtures(); let service = fakes.service(); service.enable()
    fakes.wake.fire(); await waitUntil { fakes.transcriber.starts == 1 }
    XCTAssertEqual(fakes.events, ["wake.start", "wake.stop", "presentation", "stt.start"])
    XCTAssertEqual(fakes.presentation.shows, 1)
  }

  func testTranscriptUsesSharedConversationPathOnce() async {
    let fakes = Fixtures(); let service = fakes.service(); service.enable(); fakes.wake.fire(); await waitUntil { fakes.transcriber.starts == 1 }
    fakes.transcriber.emit("hello"); await waitUntil { fakes.conversation.requests.count == 1 }; XCTAssertEqual(fakes.conversation.requests.count, 1)
    XCTAssertEqual(fakes.conversation.requests[0].0, "hello"); XCTAssertTrue(fakes.conversation.requests[0].1)
    XCTAssertEqual(fakes.synthesizer.speaks, 0)
  }

  func testSuccessfulCycleSpeaksThenRearmsOnlyWhileEnabled() async {
    let fakes = Fixtures(); let service = fakes.service(); service.enable(); fakes.wake.fire(); await waitUntil { fakes.transcriber.starts == 1 }; fakes.transcriber.emit("hello"); await waitUntil { fakes.conversation.requests.count == 1 }
    fakes.conversation.complete("advice"); await waitUntil { fakes.synthesizer.speaks == 1 }
    XCTAssertEqual(fakes.events, ["wake.start", "wake.stop", "presentation", "stt.start", "conversation", "tts"])
    fakes.synthesizer.complete(); await Task.yield(); XCTAssertEqual(fakes.wake.starts, 2)
    service.disable(); XCTAssertEqual(fakes.wake.stops, 2)
  }

  func testDisableDuringListeningCancelsWithoutRearm() async {
    let fakes = Fixtures(); let service = fakes.service(); service.enable(); fakes.wake.fire(); await waitUntil { fakes.transcriber.starts == 1 }; service.disable()
    XCTAssertEqual(fakes.transcriber.stops, 1); XCTAssertEqual(fakes.wake.starts, 1); XCTAssertEqual(fakes.synthesizer.speaks, 0)
  }

  func testDisableDuringThinkingPreventsStaleTTS() async {
    let fakes = Fixtures(); let service = fakes.service(); service.enable(); fakes.wake.fire(); await waitUntil { fakes.transcriber.starts == 1 }; fakes.transcriber.emit("hello"); await waitUntil { fakes.conversation.requests.count == 1 }; service.disable()
    fakes.conversation.complete("late"); await Task.yield(); XCTAssertEqual(fakes.synthesizer.speaks, 0); XCTAssertEqual(fakes.wake.starts, 1)
  }

  func testDisableDuringSpeakingStopsTTSAndDoesNotRearm() async {
    let fakes = Fixtures(); let service = fakes.service(); service.enable(); fakes.wake.fire(); await waitUntil { fakes.transcriber.starts == 1 }; fakes.transcriber.emit("hello"); await waitUntil { fakes.conversation.requests.count == 1 }; fakes.conversation.complete("advice"); await waitUntil { fakes.synthesizer.speaks == 1 }; service.disable()
    XCTAssertEqual(fakes.synthesizer.stops, 1); fakes.synthesizer.complete(); XCTAssertEqual(fakes.wake.starts, 1)
  }

  func testShutdownInvalidatesStaleCallbacks() async {
    let fakes = Fixtures(); let service = fakes.service(); service.enable(); fakes.wake.fire(); await waitUntil { fakes.transcriber.starts == 1 }; service.shutdown()
    fakes.transcriber.emit("late"); fakes.conversation.complete("late"); fakes.synthesizer.complete()
    XCTAssertEqual(service.coordinator.state, .disabled); XCTAssertTrue(fakes.conversation.requests.isEmpty)
    XCTAssertEqual(fakes.transcriber.stops, 1); XCTAssertEqual(fakes.synthesizer.stops, 1)
  }

  private func waitUntil(_ condition: @escaping () -> Bool) async {
    for _ in 0..<100 where !condition() { await Task.yield() }
  }
}

@MainActor private final class Fixtures {
  let wake = TestWake(); let transcriber = TestTranscriber(); let conversation = TestConversation(); let synthesizer = TestSynthesizer(); let presentation = TestPresentation(); var events: [String] = []
  func service() -> HostHandsFreeService {
    wake.events = { [weak self] value in self?.events.append(value) }
    transcriber.events = { [weak self] value in self?.events.append(value) }
    conversation.events = { [weak self] value in self?.events.append(value) }
    synthesizer.events = { [weak self] value in self?.events.append(value) }
    presentation.events = { [weak self] value in self?.events.append(value) }
    return HostHandsFreeService(presentation: ConversationPresentationModel(), conversation: conversation, showConversation: {}, wake: wake, transcriber: transcriber, synthesizer: synthesizer, handsFreePresentation: presentation)
  }
}

@MainActor private final class TestWake: NativeWakeListener { var starts = 0; var stops = 0; var callback: ((WakeWordDetectedEvent) -> Void)?; var events: ((String) -> Void)?; func start(locale: String, onDetection: @escaping (WakeWordDetectedEvent) -> Void) throws { starts += 1; events?("wake.start"); callback = onDetection }; func stop() { stops += 1; events?("wake.stop"); callback = nil }; func fire() { callback?(WakeWordDetectedEvent(eventReference: "test", phraseKey: "hola_cauco", detectedAt: Date(), confidence: 1)) } }
@MainActor private final class TestTranscriber: SpeechTranscriber { var permissionState: SpeechPermissionState = .authorized; var onDeviceAvailable = true; var state: SpeechTranscriptionState = .idle; var starts = 0; var stops = 0; var callback: ((String) -> Void)?; var events: ((String) -> Void)?; func start(locale: Locale, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void) { starts += 1; events?("stt.start"); state = .listening; callback = onTranscript }; func stop() { stops += 1; callback = nil; state = .stopped }; func emit(_ value: String) { callback?(value) } }
@MainActor private final class TestConversation: ConversationResponding { var requests: [(String, Bool)] = []; var callback: ((Result<String, Error>) -> Void)?; var events: ((String) -> Void)?; func respond(instruction: String, useReasoning: Bool, completion: @escaping (Result<String, Error>) -> Void) { requests.append((instruction, useReasoning)); events?("conversation"); callback = completion }; func cancel() { callback = nil }; func complete(_ value: String) { callback?(.success(value)); callback = nil } }
@MainActor private final class TestSynthesizer: SpeechSynthesizer { var speaks = 0; var stops = 0; var completion: (() -> Void)?; var state: SpeechSynthesisState = .idle; var events: ((String) -> Void)?; func speak(_ text: String, locale: Locale, onComplete: @escaping () -> Void, onError: @escaping (Error) -> Void) { speaks += 1; events?("tts"); state = .speaking; completion = onComplete }; func stop() { stops += 1; completion = nil; state = .stopped }; func complete() { completion?(); completion = nil } }
@MainActor private final class TestPresentation: HandsFreePresentation { var shows = 0; var events: ((String) -> Void)?; func showConversation() { shows += 1; events?("presentation") }; func updateHandsFree(state: NativeHandsFreeState, transcript: String?, response: String?) {} }
private struct TestTransport: ConversationTransport { func respond(instruction: String, useReasoning: Bool) async throws -> String { "unused" } }
