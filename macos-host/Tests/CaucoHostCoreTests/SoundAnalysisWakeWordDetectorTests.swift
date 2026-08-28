import XCTest
import AVFoundation
@testable import CaucoHostCore

final class SoundAnalysisWakeWordDetectorTests: XCTestCase {
  func testMissingPilotModelIsUnavailableAndStartFailsClosed() {
    let detector = SoundAnalysisWakeWordDetectorGateway(provider: WakeWordModelProvider(modelURL: nil))
    XCTAssertFalse(detector.availability.available)
    XCTAssertEqual(detector.availability.backendIdentifier, "coreml_temporal_features_pilot")
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

  func testDeterministicStereo48KHzConvertsToMono16KHz() throws {
    let sourceFormat = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 2)!
    let targetFormat = AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1)!
    let converter = AVAudioConverter(from: sourceFormat, to: targetFormat)!
    let input = AVAudioPCMBuffer(pcmFormat: sourceFormat, frameCapacity: 4800)!
    input.frameLength = 4800
    for channel in 0..<2 { for i in 0..<4800 { input.floatChannelData![channel][i] = channel == 0 ? 0.25 : 0.75 } }
    let output = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: 1600)!
    var supplied = false; var error: NSError?
    let status = converter.convert(to: output, error: &error) { _, status in
      if supplied { status.pointee = .endOfStream; return nil }
      supplied = true; status.pointee = .haveData; return input
    }
    XCTAssertEqual(status, .haveData)
    XCTAssertNil(error)
    XCTAssertEqual(output.format.channelCount, 1)
    XCTAssertEqual(output.frameLength, 1600)
    XCTAssertEqual(output.floatChannelData![0][800], 0.25, accuracy: 0.02)
  }
}
