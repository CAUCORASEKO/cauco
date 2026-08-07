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

public enum CoreExecutableResolutionError: LocalizedError, Equatable {
    case repositoryUnavailable
    case missing(URL)
    case notExecutable(URL)

    public var errorDescription: String? {
        switch self {
        case .repositoryUnavailable: return "Cauco repository could not be determined. Set CAUCO_REPOSITORY to the repository directory."
        case .missing(let url): return "Python virtual environment executable is missing: \(url.path)"
        case .notExecutable(let url): return "Python virtual environment executable is not executable: \(url.path)"
        }
    }
}

/// Development-only deterministic resolution. It never searches PATH or accepts command text.
public func resolveCorePython(repository: URL?, environment: [String: String] = ProcessInfo.processInfo.environment, fileManager: FileManager = .default) throws -> (repository: URL, executable: URL) {
    let configured = environment["CAUCO_REPOSITORY"].map { URL(fileURLWithPath: $0, isDirectory: true) }
    guard let root = configured ?? repository else { throw CoreExecutableResolutionError.repositoryUnavailable }
    let executable = root.standardizedFileURL.appendingPathComponent(".venv/bin/python")
    guard fileManager.fileExists(atPath: executable.path) else { throw CoreExecutableResolutionError.missing(executable) }
    guard fileManager.isExecutableFile(atPath: executable.path) else { throw CoreExecutableResolutionError.notExecutable(executable) }
    return (root.standardizedFileURL, executable)
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
