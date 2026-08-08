import Foundation

public struct NativeCapabilityDefinition: Equatable, Sendable {
  public let capability: NativeCapability
  public let permissionId: String
  public let accessMode: String
  public let exposesPersonalData: Bool
  public let confirmationRequired: Bool
  public let implementationState: String
  public let limitations: [String]
  public let method: String
}

public struct NativeCapabilityRegistry: Sendable {
  public let definitions: [NativeCapabilityDefinition]
  public init() {
    definitions = [
      .init(
        capability: .contactsStatus, permissionId: "macos.contacts.read", accessMode: "status",
        exposesPersonalData: false, confirmationRequired: false, implementationState: "implemented",
        limitations: ["authorization metadata only"], method: "contacts.status.v1"),
      .init(
        capability: .contactsSearch, permissionId: "macos.contacts.read", accessMode: "read",
        exposesPersonalData: true, confirmationRequired: true,
        implementationState: "implemented", limitations: ["name predicate only", "limit 1..20"],
        method: "contacts.search.v1"),
      .init(
        capability: .contactsGet, permissionId: "macos.contacts.read", accessMode: "read",
        exposesPersonalData: true, confirmationRequired: true,
        implementationState: "notImplemented", limitations: ["bounded opaque reference"],
        method: "contacts.get.v1"),
      .init(
        capability: .contactsListLimited, permissionId: "macos.contacts.read", accessMode: "read",
        exposesPersonalData: true, confirmationRequired: true,
        implementationState: "notImplemented", limitations: ["limit 1..20"],
        method: "contacts.list_limited.v1"),
    ]
  }
}
