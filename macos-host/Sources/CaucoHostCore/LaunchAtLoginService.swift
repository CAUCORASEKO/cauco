import Foundation
import ServiceManagement

public enum LaunchAtLoginStatus: Equatable, Sendable {
  case enabled
  case disabled
  case requiresApproval
  case failed
}

public protocol LaunchAtLoginRegistering {
  var status: SMAppService.Status { get }
  func register() throws
  func unregister() throws
}

extension SMAppService: LaunchAtLoginRegistering {}

/// The OS registration is the only source of truth; no Cauco preference is cached.
public final class LaunchAtLoginService: @unchecked Sendable {
  private let service: LaunchAtLoginRegistering

  public init(service: LaunchAtLoginRegistering = SMAppService.mainApp) {
    self.service = service
  }

  public var status: LaunchAtLoginStatus {
    switch service.status {
    case .enabled: return .enabled
    case .notRegistered: return .disabled
    case .requiresApproval: return .requiresApproval
    case .notFound: return .failed
    @unknown default: return .failed
    }
  }

  @discardableResult public func enable() -> LaunchAtLoginStatus {
    do { try service.register() } catch { return .failed }
    return status
  }

  @discardableResult public func disable() -> LaunchAtLoginStatus {
    do { try service.unregister() } catch { return .failed }
    return status
  }
}
