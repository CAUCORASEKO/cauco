import Darwin
import Foundation

public protocol CoreProcessDiagnostics: AnyObject {
  var isRunning: Bool { get }
  var processIdentifier: Int32 { get }
  var diagnosticWorkingDirectory: URL? { get }
}

public protocol OwnedCoreProcess: CoreProcessDiagnostics {
  var isRunning: Bool { get }
  var processIdentifier: Int32 { get }
  func terminate()
  func waitUntilExit()
}

extension Process: HostRuntimeProcess {
  public func configure(configuration: HostRuntimeConfiguration) throws {
    executableURL = configuration.executable
    arguments = configuration.arguments
    currentDirectoryURL = configuration.workingDirectory
    environment = configuration.environment
  }

  public func onTermination(_ handler: @escaping @Sendable () -> Void) {
    terminationHandler = { _ in handler() }
  }

  public func launch() throws { try run() }
}

extension Process {
  public var diagnosticWorkingDirectory: URL? { currentDirectoryURL }
}

public enum OwnedCoreTerminationResult: Equatable, Sendable {
  case alreadyExited
  case terminated
  case forceTerminated
  case stillRunning
}

public struct OwnedCoreProcessTerminator {
  private let now: () -> TimeInterval
  private let sleep: (TimeInterval) -> Void
  private let forceTerminate: (Int32) -> Bool

  public init(
    now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
    sleep: @escaping (TimeInterval) -> Void = { Thread.sleep(forTimeInterval: $0) },
    forceTerminate: @escaping (Int32) -> Bool = { kill($0, SIGKILL) == 0 }
  ) {
    self.now = now
    self.sleep = sleep
    self.forceTerminate = forceTerminate
  }

  public func stop(
    _ process: OwnedCoreProcess, gracefulTimeout: TimeInterval = 1.0,
    pollInterval: TimeInterval = 0.01
  ) -> OwnedCoreTerminationResult {
    guard process.isRunning else { return .alreadyExited }

    process.terminate()
    let deadline = now() + max(0, gracefulTimeout)
    while process.isRunning && now() < deadline {
      sleep(max(0.001, pollInterval))
    }
    if !process.isRunning {
      process.waitUntilExit()
      return .terminated
    }

    guard forceTerminate(process.processIdentifier) else { return .stillRunning }
    process.waitUntilExit()
    return process.isRunning ? .stillRunning : .forceTerminated
  }
}
