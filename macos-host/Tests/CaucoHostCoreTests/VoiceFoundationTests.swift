import CaucoHostCore
import XCTest

@MainActor final class VoiceFoundationTests: XCTestCase {
  func testTranscriberContractIsExplicitAndSingleSession() {
    let fake = FakeTranscriber()
    XCTAssertEqual(fake.state, .idle)
    fake.start(locale: Locale(identifier: "en-US"), onTranscript: { _ in }, onError: { _ in })
    XCTAssertEqual(fake.starts, 1)
    fake.start(locale: Locale(identifier: "en-US"), onTranscript: { _ in }, onError: { _ in })
    XCTAssertEqual(fake.starts, 1)
    fake.stop()
    XCTAssertEqual(fake.state, .stopped)
  }

  func testSynthesizerStopInvalidatesCompletion() {
    let fake = FakeSynthesizer()
    var completed = false
    fake.speak("hello", locale: Locale(identifier: "en-US"), onComplete: { completed = true }, onError: { _ in })
    fake.stop()
    fake.finish()
    XCTAssertFalse(completed)
    XCTAssertEqual(fake.state, .stopped)
  }
}

@MainActor private final class FakeTranscriber: SpeechTranscriber {
  var permissionState: SpeechPermissionState = .authorized
  var onDeviceAvailable = true
  var state: SpeechTranscriptionState = .idle
  var starts = 0
  func start(locale: Locale, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void) {
    guard state == .idle || state == .stopped else { return }
    starts += 1; state = .listening
  }
  func stop() { state = .stopped }
}

@MainActor private final class FakeSynthesizer: SpeechSynthesizer {
  var state: SpeechSynthesisState = .idle
  private var completion: (() -> Void)?
  func speak(_ text: String, locale: Locale, onComplete: @escaping () -> Void, onError: @escaping (Error) -> Void) {
    guard state == .idle else { return }
    state = .speaking; completion = onComplete
  }
  func stop() { state = .stopped; completion = nil }
  func finish() { completion?(); completion = nil; if state == .speaking { state = .completed } }
}
