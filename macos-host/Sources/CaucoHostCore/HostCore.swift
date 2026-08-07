import Foundation
import Contacts

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
        switch status { case .notDetermined: return .notRequested; case .authorized: return .granted; case .denied: return .denied; case .restricted: return .restricted; @unknown default: return .unavailable }
    }
}

public struct CoreLaunchConfiguration: Equatable, Sendable {
    public let executable: URL
    public let arguments: [String]
    public let url: URL
    public init(executable: URL, repository: URL, port: Int = 8765) {
        self.executable = executable
        self.arguments = ["-m", "uvicorn", "cauco_core.main:app", "--host", "127.0.0.1", "--port", String(port)]
        self.url = URL(string: "http://127.0.0.1:\(port)")!
        _ = repository // Repository is used to set the child working directory.
    }
}

public let repositoryPathDefaultsKey = "cauco.developmentRepositoryPath"
public let repositoryPathEnvironmentKey = "CAUCO_REPOSITORY_PATH"
public enum RepositorySource: String, Equatable, Sendable { case configured = "Configured", environment = "Environment", developmentFallback = "Development fallback" }

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
        case .missingPython(let url): return "Python virtual environment executable is missing: \(url.path)"
        case .pythonNotRegular(let url): return "Python virtual environment executable is not a regular file: \(url.path)"
        case .pythonNotExecutable(let url): return "Python virtual environment executable is not executable: \(url.path)"
        }
    }
}

public struct RepositoryConfiguration: Equatable, Sendable {
    public let repository: URL
    public let executable: URL
    public let source: RepositorySource

    public static func resolve(userDefaults: UserDefaults = .standard, environment: [String: String] = ProcessInfo.processInfo.environment, workingDirectory: URL? = URL(fileURLWithPath: FileManager.default.currentDirectoryPath), fileManager: FileManager = .default) throws -> RepositoryConfiguration {
        let configured = userDefaults.string(forKey: repositoryPathDefaultsKey).flatMap { $0.isEmpty ? nil : URL(fileURLWithPath: $0, isDirectory: true) }
        let candidate = configured ?? environment[repositoryPathEnvironmentKey].flatMap { $0.isEmpty ? nil : URL(fileURLWithPath: $0, isDirectory: true) }
        if let candidate { var value = try validate(candidate, fileManager: fileManager); value = RepositoryConfiguration(repository: value.repository, executable: value.executable, source: configured == nil ? .environment : .configured); return value }
        if let workingDirectory, isRepositoryBuildTree(workingDirectory, fileManager: fileManager) { let value = try validate(workingDirectory, fileManager: fileManager); return RepositoryConfiguration(repository: value.repository, executable: value.executable, source: .developmentFallback) }
        throw RepositoryResolutionError.unconfigured
    }

    public static func validate(_ candidate: URL, fileManager: FileManager = .default) throws -> RepositoryConfiguration {
        let root = candidate.standardizedFileURL
        guard root.path != "/" else { throw RepositoryResolutionError.rootRejected }
        guard fileManager.fileExists(atPath: root.path), (try? root.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true else { throw RepositoryResolutionError.missingDirectory(root) }
        guard root == root.resolvingSymlinksInPath().standardizedFileURL else { throw RepositoryResolutionError.symlinkedRoot(root) }
        let manifest = root.appendingPathComponent("core").appendingPathComponent("pyproject.toml")
        guard fileManager.fileExists(atPath: manifest.path) else { throw RepositoryResolutionError.missingCoreManifest(manifest) }
        let python = root.appendingPathComponent(".venv").appendingPathComponent("bin").appendingPathComponent("python")
        guard fileManager.fileExists(atPath: python.path) else { throw RepositoryResolutionError.missingPython(python) }
        let resolvedPython = python.resolvingSymlinksInPath().standardizedFileURL
        guard fileManager.fileExists(atPath: resolvedPython.path) else { throw RepositoryResolutionError.missingPython(python) }
        guard (try? resolvedPython.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else { throw RepositoryResolutionError.pythonNotRegular(python) }
        guard fileManager.isExecutableFile(atPath: resolvedPython.path) else { throw RepositoryResolutionError.pythonNotExecutable(python) }
        return RepositoryConfiguration(repository: root, executable: resolvedPython, source: .configured)
    }

    private static func isRepositoryBuildTree(_ url: URL, fileManager: FileManager) -> Bool {
        let root = url.standardizedFileURL
        return root.path != "/" && fileManager.fileExists(atPath: root.appendingPathComponent("core").appendingPathComponent("pyproject.toml").path) && fileManager.fileExists(atPath: root.appendingPathComponent(".venv").appendingPathComponent("bin").appendingPathComponent("python").path)
    }
}

public func resolveCorePython(repository: URL?, environment: [String: String] = ProcessInfo.processInfo.environment, fileManager: FileManager = .default) throws -> (repository: URL, executable: URL) {
    let config = try RepositoryConfiguration.validate(repository ?? URL(fileURLWithPath: "/"), fileManager: fileManager)
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

public func boundedDiagnostic(_ text: String, limit: Int = 1_000) -> String { String(text.suffix(limit)) }

public enum HealthProbeResult: Equatable, Sendable { case retry, healthy, processExited, timedOut }

public struct CoreHealthPolicy: Sendable {
    public let timeoutMilliseconds: Int
    public let retryMilliseconds: Int
    public init(timeoutMilliseconds: Int = 15_000, retryMilliseconds: Int = 350) { self.timeoutMilliseconds = timeoutMilliseconds; self.retryMilliseconds = retryMilliseconds }
    public func nextResult(processRunning: Bool, elapsedMilliseconds: Int, probeHealthy: Bool) -> HealthProbeResult {
        if probeHealthy { return .healthy }
        if !processRunning { return .processExited }
        return elapsedMilliseconds >= timeoutMilliseconds ? .timedOut : .retry
    }
}
