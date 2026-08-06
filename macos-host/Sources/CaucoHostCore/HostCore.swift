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
        _ = repository // Repository discovery is deliberately external to the fixed argv.
    }
}

public func isLocalCoreURL(_ url: URL) -> Bool {
    url.scheme == "http" && (url.host == "127.0.0.1" || url.host == "localhost") && url.port != nil
}

public func boundedDiagnostic(_ text: String, limit: Int = 4_000) -> String { String(text.suffix(limit)) }
