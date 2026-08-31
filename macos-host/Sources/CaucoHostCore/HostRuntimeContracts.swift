import Foundation

/// Immutable inputs required to launch and supervise the local Core process.
/// Broker credentials and socket paths are created internally by HostRuntime.
public struct HostRuntimeConfiguration: Sendable {
  public let executable: URL
  public let arguments: [String]
  public let workingDirectory: URL
  public let environment: [String: String]
  public let coreBaseURL: URL
  public let healthPolicy: CoreHealthPolicy

  public init(
    executable: URL,
    arguments: [String],
    workingDirectory: URL,
    environment: [String: String] = [:],
    coreBaseURL: URL,
    healthPolicy: CoreHealthPolicy = CoreHealthPolicy()
  ) {
    self.executable = executable
    self.arguments = arguments
    self.workingDirectory = workingDirectory
    self.environment = environment
    self.coreBaseURL = coreBaseURL
    self.healthPolicy = healthPolicy
  }
}

public enum HostRuntimeUpdate {
  case starting
  case brokerStarted
  case processStarted(CoreLaunchDiagnosticSnapshot)
  case healthCheck(CoreLaunchDiagnosticSnapshot, healthy: Bool)
  case healthy(CoreLaunchDiagnosticSnapshot)
  case processExited(snapshot: CoreLaunchDiagnosticSnapshot, reason: String, status: Int32)
  case failed(message: String)
  case stopped
}

public protocol HostRuntimeProcessFactory: AnyObject {
  func makeProcess(configuration: HostRuntimeConfiguration) throws -> OwnedCoreProcess
}

public protocol HostRuntimeBrokerFactory: AnyObject {
  func makeBrokerServer(
    localWakeHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void
  ) throws -> NativeBrokerTransportServer
}
