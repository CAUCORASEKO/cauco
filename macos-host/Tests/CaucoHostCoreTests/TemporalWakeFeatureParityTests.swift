import XCTest
@testable import CaucoHostCore

final class TemporalWakeFeatureParityTests: XCTestCase {
  func testDeterministicFixtureHasExpectedShape() throws {
    let path = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
      .appendingPathComponent("../wake-model/local-output/coreml-pilot/feature-fixture.json")
    guard FileManager.default.fileExists(atPath: path.path) else {
      throw XCTSkip("generate feature fixture first")
    }
    let object = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as! [String: Any]
    let expected = (object["values"] as! [NSNumber]).map(\.doubleValue)
    XCTAssertEqual(expected.count, 348)
    let n = 16_000
    let samples = (0..<n).map { i -> Double in
      let t = Double(i) / 16_000
      let value = 0.18 * sin(2 * Double.pi * 440 * t) + 0.07 * sin(2 * Double.pi * 997 * t + 0.31)
      return Double(Int16(max(-32768, min(32767, Int(value * 32768))))) / 32768.0
    }
    let actual = try TemporalWakeFeatureExtractor().extract(samples: samples)
    let errors = zip(actual, expected).map { abs($0 - $1) }
    print("parity max=\(errors.max() ?? .infinity) mean=\(errors.reduce(0,+)/Double(errors.count)) actual0=\(actual[0]) expected0=\(expected[0])")
    XCTAssertEqual(actual.count, 348)
    XCTAssertLessThan(errors.max() ?? .infinity, 1e-8)
    XCTAssertLessThan(errors.reduce(0, +) / Double(errors.count), 1e-9)
  }

  func testDeterministicWindowBenchmark() throws {
    let samples = (0..<16_000).map { i -> Double in
      let t = Double(i) / 16_000
      return 0.18 * sin(2 * Double.pi * 440 * t) + 0.07 * sin(2 * Double.pi * 997 * t + 0.31)
    }
    let extractor = TemporalWakeFeatureExtractor(); _ = try extractor.extract(samples: samples)
    let started = ProcessInfo.processInfo.systemUptime
    for _ in 0..<5 { _ = try extractor.extract(samples: samples) }
    print("optimized 1-second feature average_ms=\((ProcessInfo.processInfo.systemUptime - started) * 200)")
  }
}
