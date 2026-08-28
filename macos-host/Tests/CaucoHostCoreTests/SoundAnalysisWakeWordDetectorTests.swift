import XCTest
@testable import CaucoHostCore

final class SoundAnalysisWakeWordDetectorTests: XCTestCase {
  func testMissingPilotModelIsUnavailableAndStartFailsClosed() {
    let detector = SoundAnalysisWakeWordDetectorGateway(provider: WakeWordModelProvider(modelURL: nil))
    XCTAssertFalse(detector.availability.available)
    XCTAssertEqual(detector.availability.backendIdentifier, "avfoundation_soundanalysis_pilot")
    XCTAssertThrowsError(try detector.start(configuration: .init(phraseKey: "hola_cauco", locale: "es-ES")) { _ in })
    detector.stop()
  }

  func testPilotConfigurationIsBounded() {
    let configuration = WakeWordPilotConfiguration.default
    XCTAssertEqual(configuration.phraseKey, "hola_cauco")
    XCTAssertEqual(configuration.modelLabel, "hola_cauco")
    XCTAssertGreaterThan(configuration.confidenceThreshold, 0)
    XCTAssertLessThanOrEqual(configuration.confidenceThreshold, 1)
    XCTAssertGreaterThan(configuration.consecutiveWindows, 1)
  }
}
