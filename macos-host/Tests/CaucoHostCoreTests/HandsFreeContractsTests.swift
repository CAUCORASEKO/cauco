import XCTest
@testable import CaucoHostCore

final class HandsFreeContractsTests: XCTestCase {
  func testLegalStateMachinePathAndIllegalSkip() throws {
    let path: [NativeHandsFreeState] = [.disabled, .waitingForWake, .wakeDetected,
      .requestingSpeechPermission, .listening, .transcribing, .thinking, .speaking,
      .rearming, .waitingForWake]
    for pair in zip(path, path.dropFirst()) {
      XCTAssertNoThrow(try NativeHandsFreeStateMachine.transition(pair.0, to: pair.1))
    }
    XCTAssertThrowsError(try NativeHandsFreeStateMachine.transition(.waitingForWake, to: .speaking))
  }

  func testGenerationInvalidatesEveryOlderCallbackToken() {
    let generation = NativeHandsFreeGeneration()
    let token = generation.current()
    XCTAssertTrue(generation.isCurrent(token))
    generation.advance()
    XCTAssertFalse(generation.isCurrent(token))
    XCTAssertTrue(generation.isCurrent(generation.current()))
  }

  func testWakeFanoutPreservesCoreAndLocalCallbacks() throws {
    let detector = ContractFakeWakeDetector()
    var coreEvents = 0; var localEvents = 0
    let service = WakeWordCapabilityService(
      detector: detector,
      eventHandler: { _ in coreEvents += 1 },
      localEventHandler: { _ in localEvents += 1 })
    try service.start(configuration: WakeWordDetectorConfiguration(phraseKey: "hola_cauco", locale: "es-ES"))
    detector.emit()
    XCTAssertEqual(coreEvents, 1); XCTAssertEqual(localEvents, 1)
  }
}

private final class ContractFakeWakeDetector: WakeWordDetectorGateway, @unchecked Sendable {
  let availability = WakeWordDetectorAvailability(available: true, backendIdentifier: "test", permissionStatus: .granted)
  private var callback: ((WakeWordDetectionSignal) -> Void)?
  func start(configuration: WakeWordDetectorConfiguration, detectionHandler: @escaping @Sendable (WakeWordDetectionSignal) -> Void) throws { callback = detectionHandler }
  func stop() { callback = nil }
  func emit() { callback?(WakeWordDetectionSignal(confidence: 0.9)) }
}
