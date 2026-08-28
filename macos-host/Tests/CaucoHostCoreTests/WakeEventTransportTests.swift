import Darwin
import Foundation
import XCTest

@testable import CaucoHostCore

final class WakeEventTransportTests: XCTestCase {
  func testSendsOneBoundedNewlineDelimitedFrame() throws {
    let server = try LocalWakeSocket()
    let expectation = expectation(description: "frame")
    server.accept { data in
      defer { expectation.fulfill() }
      let lines = data.split(separator: 10)
      XCTAssertEqual(lines.count, 1)
      let object = try? JSONSerialization.jsonObject(with: Data(lines[0])) as? [String: Any]
      XCTAssertEqual(Set(object?.keys ?? []), Set(["type", "event_reference", "phrase_key", "detected_at", "confidence"]))
      XCTAssertEqual(object?["type"] as? String, "wakeword.detected")
      XCTAssertNil(object?["audio"])
      XCTAssertNil(object?["metadata"])
    }
    CaucoWakeEventTransport(socketURL: server.url).send(WakeWordDetectedEvent(eventReference: "wakeevt_test", phraseKey: "hola_cauco", detectedAt: Date(timeIntervalSince1970: 1), confidence: 0.5))
    waitForExpectations(timeout: 1)
  }

  func testUnavailableAndOversizedSocketsFailClosed() {
    CaucoWakeEventTransport(socketURL: URL(fileURLWithPath: "/tmp/does-not-exist-cauco.sock")).send(WakeWordDetectedEvent(eventReference: "wakeevt_test", phraseKey: "hola_cauco", detectedAt: Date(), confidence: nil))
    let oversized = String(repeating: "x", count: 300)
    CaucoWakeEventTransport(socketURL: URL(fileURLWithPath: "/tmp/\(oversized)")).send(WakeWordDetectedEvent(eventReference: "wakeevt_test", phraseKey: "hola_cauco", detectedAt: Date(), confidence: nil))
  }
}

private final class LocalWakeSocket {
  let url: URL
  private let fd: Int32
  init() throws {
    url = URL(fileURLWithPath: "/tmp/cauco-wake-test-\(UUID().uuidString).sock")
    fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { throw POSIXError(.EIO) }
    var address = sockaddr_un(); address.sun_family = sa_family_t(AF_UNIX)
    withUnsafeMutableBytes(of: &address.sun_path) { $0.initializeMemory(as: UInt8.self, repeating: 0); $0.copyBytes(from: Array(url.path.utf8)) }
    let length = socklen_t(MemoryLayout<sa_family_t>.size + url.path.utf8.count + 1)
    let result = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, length) } }
    guard result == 0, Darwin.listen(fd, 1) == 0 else { close(fd); throw POSIXError(.EIO) }
  }
  func accept(_ callback: @escaping (Data) -> Void) {
    DispatchQueue.global().async { [fd] in
      let client = Darwin.accept(fd, nil, nil); guard client >= 0 else { return }; defer { close(client) }
      var data = Data(); var buffer = [UInt8](repeating: 0, count: 4096)
      let count = recv(client, &buffer, buffer.count, 0); if count > 0 { data.append(buffer, count: count) }; callback(data)
    }
  }
  deinit { close(fd); unlink(url.path) }
}
