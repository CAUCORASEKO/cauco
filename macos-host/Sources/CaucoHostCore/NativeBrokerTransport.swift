import Darwin
import Foundation
import Security

public struct NativeBrokerTransportEnvelope: Codable, Sendable {
  public let token: String
  public let request: NativeCapabilityRequest
}

public final class NativeBrokerTransportServer: @unchecked Sendable {
  public static let maxRequestBytes = 16 * 1024
  public static let maxResponseBytes = 32 * 1024

  public let socketURL: URL
  public let token: String

  private let descriptor: Int32
  private let acceptQueue = DispatchQueue(label: "com.cauco.host.native-broker.accept")
  private let workerQueue = DispatchQueue(
    label: "com.cauco.host.native-broker.workers", attributes: .concurrent)
  private let workerSlots = DispatchSemaphore(value: 4)
  private let broker: NativeCapabilityBroker

  public init(broker: NativeCapabilityBroker) throws {
    self.broker = broker
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
      "cauco-\(UUID().uuidString.prefix(8))", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    socketURL = directory.appendingPathComponent("broker.sock")
    token = try Self.randomToken()

    let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else {
      throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
    }
    descriptor = fd
  }

  public func start() throws {
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)
    let pathCapacity = MemoryLayout<sockaddr_un>.size - MemoryLayout<sa_family_t>.size
    withUnsafeMutablePointer(to: &address.sun_path) { pathPointer in
      pathPointer.withMemoryRebound(to: CChar.self, capacity: pathCapacity) { cPath in
        socketURL.path.withCString { path in
          strncpy(cPath, path, pathCapacity - 1)
        }
      }
    }

    unlink(socketURL.path)
    let addressLength = socklen_t(
      MemoryLayout<sa_family_t>.size + socketURL.path.utf8.count + 1)
    let bindResult = withUnsafePointer(to: &address) { pointer in
      pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        Darwin.bind(descriptor, $0, addressLength)
      }
    }
    guard bindResult == 0 else {
      throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
    }
    guard chmod(socketURL.path, 0o600) == 0 else {
      throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
    }
    guard Darwin.listen(descriptor, 8) == 0 else {
      throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
    }
    acceptQueue.async { [self] in acceptLoop() }
  }

  public func stop() {
    broker.shutdown()
    Darwin.shutdown(descriptor, SHUT_RDWR)
    close(descriptor)
    try? FileManager.default.removeItem(at: socketURL)
    try? FileManager.default.removeItem(at: socketURL.deletingLastPathComponent())
  }

  private func acceptLoop() {
    while true {
      let client = Darwin.accept(descriptor, nil, nil)
      guard client >= 0 else { return }
      workerSlots.wait()
      workerQueue.async { [self] in
        defer { workerSlots.signal() }
        handle(client)
      }
    }
  }

  private func handle(_ client: Int32) {
    defer { close(client) }
    var data = Data()
    var buffer = [UInt8](repeating: 0, count: 2048)
    while data.count <= Self.maxRequestBytes {
      let count = recv(client, &buffer, buffer.count, 0)
      if count <= 0 { return }
      data.append(buffer, count: count)
      if buffer.prefix(count).contains(10) { break }
    }
    guard data.count <= Self.maxRequestBytes else {
      sendError(client, "request_too_large")
      return
    }
    guard let line = String(data: data.prefix { $0 != 10 }, encoding: .utf8),
      let envelope = try? JSONDecoder().decode(
        NativeBrokerTransportEnvelope.self, from: Data(line.utf8))
    else {
      sendError(client, "invalid_request")
      return
    }
    guard constantTimeEqual(envelope.token, token) else {
      sendError(client, "invalid_token")
      return
    }
    let response = broker.handle(envelope.request)
    guard let responseData = try? JSONEncoder().encode(response),
      responseData.count <= Self.maxResponseBytes
    else {
      sendError(client, "response_too_large")
      return
    }
    sendData(responseData, to: client)
    sendData(Data("\n".utf8), to: client)
  }

  private func sendError(_ client: Int32, _ code: String) {
    sendData(Data("{\"error\":{\"code\":\"\(code)\"}}\n".utf8), to: client)
  }

  private func sendData(_ data: Data, to client: Int32) {
    data.withUnsafeBytes { bytes in
      _ = send(client, bytes.baseAddress, data.count, 0)
    }
  }

  private func constantTimeEqual(_ lhs: String, _ rhs: String) -> Bool {
    let left = Array(lhs.utf8)
    let right = Array(rhs.utf8)
    var difference = UInt8(left.count ^ right.count)
    for index in 0..<max(left.count, right.count) {
      difference |= (index < left.count ? left[index] : 0)
        ^ (index < right.count ? right[index] : 0)
    }
    return difference == 0
  }

  private static func randomToken() throws -> String {
    var bytes = [UInt8](repeating: 0, count: 32)
    guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
      throw POSIXError(.EIO)
    }
    return Data(bytes).base64EncodedString()
  }
}
