import Contacts
import EventKit
import Foundation

public enum ContactsAuthorization: Equatable, Sendable {
  case notRequested, granted, denied, restricted, unavailable
}

public protocol ContactsPermissionGateway {
  func authorizationState() -> ContactsAuthorization
  func requestAccess(completion: @escaping (ContactsAuthorization) -> Void)
}

public final class NativeContactsPermissionGateway: ContactsPermissionGateway {
  private let store = CNContactStore()
  public init() {}

  public func authorizationState() -> ContactsAuthorization {
    Self.map(CNContactStore.authorizationStatus(for: .contacts))
  }

  public func requestAccess(completion: @escaping (ContactsAuthorization) -> Void) {
    store.requestAccess(for: .contacts) { _, _ in
      DispatchQueue.main.async { completion(self.authorizationState()) }
    }
  }

  public static func map(_ status: CNAuthorizationStatus) -> ContactsAuthorization {
    switch status {
    case .notDetermined: return .notRequested
    case .authorized: return .granted
    case .denied: return .denied
    case .restricted: return .restricted
    @unknown default: return .unavailable
    }
  }
}

public enum CalendarAuthorization: Equatable, Sendable { case notRequested, granted, denied, restricted, unavailable }
public protocol CalendarPermissionGateway {
  func authorizationState() -> CalendarAuthorization
  func requestAccess(completion: @escaping (CalendarAuthorization) -> Void)
}
public final class NativeCalendarPermissionGateway: CalendarPermissionGateway {
  private let store = EKEventStore()
  public init() {}
  public func authorizationState() -> CalendarAuthorization {
    if #available(macOS 14.0, *) {
      return Self.map(EKEventStore.authorizationStatus(for: .event))
    }
    return Self.mapLegacy(EKEventStore.authorizationStatus(for: .event))
  }
  public func requestAccess(completion: @escaping (CalendarAuthorization) -> Void) {
    let finish: () -> Void = { DispatchQueue.main.async { completion(self.authorizationState()) } }
    if #available(macOS 14.0, *) {
      store.requestFullAccessToEvents { _, _ in finish() }
    } else {
      store.requestAccess(to: .event) { _, _ in finish() }
    }
  }
  @available(macOS 14.0, *)
  public static func map(_ status: EKAuthorizationStatus) -> CalendarAuthorization {
    switch status {
    case .fullAccess: return .granted
    case .writeOnly: return .unavailable
    case .notDetermined: return .notRequested
    case .denied: return .denied
    case .restricted: return .restricted
    @unknown default: return .unavailable
    }
  }
  public static func mapLegacy(_ status: EKAuthorizationStatus) -> CalendarAuthorization {
    switch status {
    case .fullAccess: return .granted
    case .writeOnly: return .unavailable
    case .authorized: return .granted
    case .notDetermined: return .notRequested
    case .denied: return .denied
    case .restricted: return .restricted
    @unknown default: return .unavailable
    }
  }
}

public struct CoreLaunchConfiguration: Equatable, Sendable {
  public let executable: URL
  public let arguments: [String]
  public let url: URL
  public init(executable: URL, repository: URL, port: Int = 8765) {
    self.executable = executable
    self.arguments = [
      "-m", "uvicorn", "cauco_core.main:app", "--host", "127.0.0.1", "--port", String(port),
    ]
    self.url = URL(string: "http://127.0.0.1:\(port)")!
    _ = repository  // Repository is used to set the child working directory.
  }
}

public let repositoryPathDefaultsKey = "cauco.developmentRepositoryPath"
public let repositoryPathEnvironmentKey = "CAUCO_REPOSITORY_PATH"
public enum RepositorySource: String, Equatable, Sendable {
  case configured = "Configured"
  case environment = "Environment"
  case developmentFallback = "Development fallback"
}

public enum RepositoryResolutionError: LocalizedError, Equatable {
  case unconfigured
  case rootRejected
  case missingDirectory(URL)
  case symlinkedRoot(URL)
  case missingCoreManifest(URL)
  case missingPython(URL)
  case pythonNotRegular(URL)
  case pythonNotExecutable(URL)

  public var errorDescription: String? {
    switch self {
    case .unconfigured: return "Repository path is not configured."
    case .rootRejected: return "The filesystem root is not a valid Cauco repository."
    case .missingDirectory(let url): return "Repository directory is missing: \(url.path)"
    case .symlinkedRoot(let url): return "Repository path must not be a symlink: \(url.path)"
    case .missingCoreManifest(let url): return "Cauco Core manifest is missing: \(url.path)"
    case .missingPython(let url):
      return "Python virtual environment executable is missing: \(url.path)"
    case .pythonNotRegular(let url):
      return "Python virtual environment executable is not a regular file: \(url.path)"
    case .pythonNotExecutable(let url):
      return "Python virtual environment executable is not executable: \(url.path)"
    }
  }
}

public struct RepositoryConfiguration: Equatable, Sendable {
  public let repository: URL
  public let executable: URL
  public let source: RepositorySource

  public static func resolve(
    userDefaults: UserDefaults = .standard,
    environment: [String: String] = ProcessInfo.processInfo.environment,
    workingDirectory: URL? = URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
    fileManager: FileManager = .default
  ) throws -> RepositoryConfiguration {
    let configured = userDefaults.string(forKey: repositoryPathDefaultsKey).flatMap {
      $0.isEmpty ? nil : URL(fileURLWithPath: $0, isDirectory: true)
    }
    let candidate =
      configured
      ?? environment[repositoryPathEnvironmentKey].flatMap {
        $0.isEmpty ? nil : URL(fileURLWithPath: $0, isDirectory: true)
      }
    if let candidate {
      var value = try validate(candidate, fileManager: fileManager)
      value = RepositoryConfiguration(
        repository: value.repository, executable: value.executable,
        source: configured == nil ? .environment : .configured)
      return value
    }
    if let workingDirectory, isRepositoryBuildTree(workingDirectory, fileManager: fileManager) {
      let value = try validate(workingDirectory, fileManager: fileManager)
      return RepositoryConfiguration(
        repository: value.repository, executable: value.executable, source: .developmentFallback)
    }
    throw RepositoryResolutionError.unconfigured
  }

  public static func validate(_ candidate: URL, fileManager: FileManager = .default) throws
    -> RepositoryConfiguration
  {
    let root = candidate.standardizedFileURL
    guard root.path != "/" else { throw RepositoryResolutionError.rootRejected }
    guard fileManager.fileExists(atPath: root.path),
      (try? root.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
    else { throw RepositoryResolutionError.missingDirectory(root) }
    guard root == root.resolvingSymlinksInPath().standardizedFileURL else {
      throw RepositoryResolutionError.symlinkedRoot(root)
    }
    let manifest = root.appendingPathComponent("core").appendingPathComponent("pyproject.toml")
    guard fileManager.fileExists(atPath: manifest.path) else {
      throw RepositoryResolutionError.missingCoreManifest(manifest)
    }
    let python = root.appendingPathComponent(".venv").appendingPathComponent("bin")
      .appendingPathComponent("python")
    guard fileManager.fileExists(atPath: python.path) else {
      throw RepositoryResolutionError.missingPython(python)
    }
    let resolvedPython = python.resolvingSymlinksInPath().standardizedFileURL
    guard fileManager.fileExists(atPath: resolvedPython.path) else {
      throw RepositoryResolutionError.missingPython(python)
    }
    guard (try? resolvedPython.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true
    else { throw RepositoryResolutionError.pythonNotRegular(python) }
    guard fileManager.isExecutableFile(atPath: resolvedPython.path) else {
      throw RepositoryResolutionError.pythonNotExecutable(python)
    }
    // Keep the virtualenv entrypoint as the launch URL. The resolved destination is
    // used only to validate that the entrypoint ultimately targets an executable file;
    // launching the destination would bypass virtualenv context (and can select Homebrew).
    return RepositoryConfiguration(repository: root, executable: python, source: .configured)
  }

  private static func isRepositoryBuildTree(_ url: URL, fileManager: FileManager) -> Bool {
    let root = url.standardizedFileURL
    return root.path != "/"
      && fileManager.fileExists(
        atPath: root.appendingPathComponent("core").appendingPathComponent("pyproject.toml").path)
      && fileManager.fileExists(
        atPath: root.appendingPathComponent(".venv").appendingPathComponent("bin")
          .appendingPathComponent("python").path)
  }
}

public func resolveCorePython(
  repository: URL?, environment: [String: String] = ProcessInfo.processInfo.environment,
  fileManager: FileManager = .default
) throws -> (repository: URL, executable: URL) {
  let config = try RepositoryConfiguration.validate(
    repository ?? URL(fileURLWithPath: "/"), fileManager: fileManager)
  _ = environment
  return (config.repository, config.executable)
}

public enum CoreLifecycleState: Equatable, Sendable { case stopped, starting, online, unavailable }

public struct CoreLifecycleRules: Sendable {
  public init() {}
  public func canStart(ownedProcessExists: Bool) -> Bool { !ownedProcessExists }
  public func stateAfterLaunchFailure() -> CoreLifecycleState { .unavailable }
  public func stateAfterStartupTimeout() -> CoreLifecycleState { .unavailable }
  public func canStop(ownedProcessExists: Bool) -> Bool { ownedProcessExists }
}

public func isLocalCoreURL(_ url: URL) -> Bool {
  url.scheme == "http" && url.host == "127.0.0.1" && url.port != nil
}

public func boundedDiagnostic(_ text: String, limit: Int = 1_000) -> String {
  String(text.suffix(limit))
}

public func sanitizedDiagnosticLine(_ line: String, limit: Int = 240) -> String {
  let clean = line.unicodeScalars.map { $0.value < 0x20 || $0.value == 0x7f ? " " : String($0) }
    .joined()
  return String(clean.prefix(limit))
}

public func boundedDiagnosticTail(_ text: String, maxLines: Int) -> [String] {
  Array(
    text.split(omittingEmptySubsequences: true, whereSeparator: { $0 == "\n" || $0 == "\r" })
      .suffix(maxLines)
  ).map { sanitizedDiagnosticLine(String($0)) }
}

public struct CoreLaunchDiagnosticSnapshot: Equatable, Sendable {
  public let pid: Int32
  public var running: Bool
  public let executable: URL
  public let workingDirectory: URL
  public let arguments: [String]
  public let launchedAt: Date
  public var lifecycleState: CoreLifecycleState
  public var terminationReason: String?
  public var terminationStatus: Int32?
  public var exitedBeforeHealth: Bool
  public var stderrTail: [String]
  public var stdoutTail: [String]
  public var latestHealthCheck: String

  public init(
    process: Process, configuration: CoreLaunchConfiguration, state: CoreLifecycleState,
    launchedAt: Date = Date()
  ) {
    self.pid = process.processIdentifier
    self.running = process.isRunning
    self.executable = configuration.executable
    self.workingDirectory = process.currentDirectoryURL ?? URL(fileURLWithPath: "")
    self.arguments = configuration.arguments
    self.launchedAt = launchedAt
    self.lifecycleState = state
    self.terminationReason = nil
    self.terminationStatus = nil
    self.exitedBeforeHealth = false
    self.stderrTail = []
    self.stdoutTail = []
    self.latestHealthCheck = "not started"
  }
}

public enum HealthProbeResult: Equatable, Sendable { case retry, healthy, processExited, timedOut }

public struct CoreHealthPolicy: Sendable {
  public let timeoutMilliseconds: Int
  public let retryMilliseconds: Int
  public init(timeoutMilliseconds: Int = 15_000, retryMilliseconds: Int = 350) {
    self.timeoutMilliseconds = timeoutMilliseconds
    self.retryMilliseconds = retryMilliseconds
  }
  public func nextResult(processRunning: Bool, elapsedMilliseconds: Int, probeHealthy: Bool)
    -> HealthProbeResult
  {
    if probeHealthy { return .healthy }
    if !processRunning { return .processExited }
    return elapsedMilliseconds >= timeoutMilliseconds ? .timedOut : .retry
  }
}
