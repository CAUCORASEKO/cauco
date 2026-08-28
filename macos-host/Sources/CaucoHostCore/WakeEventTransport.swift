import Foundation
import Darwin

public final class CaucoWakeEventTransport: @unchecked Sendable {
  public let socketURL: URL
  public init(socketURL: URL) { self.socketURL = socketURL }
  public func send(_ event: WakeWordDetectedEvent) {
    let path = socketURL.path
    var pathBytes = Array(path.utf8)
    let capacity = MemoryLayout<sockaddr_un>.size - MemoryLayout<sa_family_t>.size
    guard pathBytes.count < capacity else { return }
    let iso = ISO8601DateFormatter().string(from: event.detectedAt)
    var payload: [String: Any] = ["type": "wakeword.detected", "event_reference": event.eventReference, "phrase_key": event.phraseKey, "detected_at": iso, "confidence": event.confidence as Any]
    if event.confidence == nil { payload["confidence"] = NSNull() }
    guard let data = try? JSONSerialization.data(withJSONObject: payload) else { return }
    let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0); guard fd >= 0 else { return }
    defer { close(fd) }
    var address = sockaddr_un(); address.sun_family = sa_family_t(AF_UNIX)
    withUnsafeMutableBytes(of: &address.sun_path) { buffer in
      buffer.initializeMemory(as: UInt8.self, repeating: 0)
      buffer.copyBytes(from: pathBytes)
    }
    let length = socklen_t(MemoryLayout<sa_family_t>.size + pathBytes.count + 1)
    let connected = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.connect(fd, $0, length) } }
    guard connected == 0 else { return }
    var frame = data; frame.append(10)
    var sent = 0
    while sent < frame.count {
      let count = frame.withUnsafeBytes { Darwin.send(fd, $0.baseAddress!.advanced(by: sent), frame.count - sent, 0) }
      if count <= 0 { return }
      sent += count
    }
  }
}
