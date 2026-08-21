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
        implementationState: "implemented", limitations: ["bounded opaque reference"],
        method: "contacts.get.v1"),
      .init(
        capability: .contactsListLimited, permissionId: "macos.contacts.read", accessMode: "read",
        exposesPersonalData: true, confirmationRequired: true,
        implementationState: "implemented", limitations: ["bounded enumeration", "limit 1..20"],
        method: "contacts.list_limited.v1"),
      .init(capability: .calendarStatus, permissionId: "macos.calendar.read", accessMode: "status", exposesPersonalData: false, confirmationRequired: false, implementationState: "implemented", limitations: ["authorization metadata only"], method: "calendar.status.v1"),
      .init(capability: .calendarCalendarsList, permissionId: "macos.calendar.read", accessMode: "read", exposesPersonalData: true, confirmationRequired: true, implementationState: "implemented", limitations: ["bounded enumeration", "limit 1..50"], method: "calendar.calendars.list.v1"),
      .init(capability: .calendarEventsRange, permissionId: "macos.calendar.read", accessMode: "read", exposesPersonalData: true, confirmationRequired: true, implementationState: "implemented", limitations: ["bounded range", "limit 1..100"], method: "calendar.events.range.v1"),
      .init(capability: .calendarEventsGet, permissionId: "macos.calendar.read", accessMode: "read", exposesPersonalData: true, confirmationRequired: true, implementationState: "implemented", limitations: ["bounded opaque reference"], method: "calendar.events.get.v1"),
      .init(capability: .calendarEventsCreate, permissionId: "macos.calendar.read", accessMode: "write", exposesPersonalData: true, confirmationRequired: true, implementationState: "implemented", limitations: ["bounded payload", "no attendees or recurrence"], method: "calendar.events.create.v1"),
      .init(
        capability: .mailAccountsList, permissionId: "macos.automation.mail",
        accessMode: "read", exposesPersonalData: true, confirmationRequired: true,
        implementationState: "implemented",
        limitations: [
          "bounded enumeration", "maximum 20 accounts", "metadata only",
          "opaque account references", "no native identifiers",
        ],
        method: "mail.accounts.list.v1"),
      .init(
        capability: .mailMailboxesList, permissionId: "macos.automation.mail",
        accessMode: "read", exposesPersonalData: true, confirmationRequired: true,
        implementationState: "implemented",
        limitations: [
          "single opaque account reference", "maximum 100 mailboxes", "metadata only",
          "opaque mailbox references", "no native identifiers",
        ],
        method: "mail.mailboxes.list.v1"),
      .init(
        capability: .mailMessagesList, permissionId: "macos.automation.mail",
        accessMode: "read", exposesPersonalData: true, confirmationRequired: true,
        implementationState: "implemented",
        limitations: [
          "One explicitly discovered opaque mailbox reference",
          "metadata only",
          "limit 1..20",
          "opaque message references",
          "no body or attachments",
        ],
        method: "mail.messages.list.v1"),
      .init(
        capability: .mailDraftCreate, permissionId: "macos.automation.mail",
        accessMode: "write", exposesPersonalData: true, confirmationRequired: true,
        implementationState: "implemented",
        limitations: ["draft creation only", "single recipient", "plain text", "no attachments"],
        method: "mail.draft.create.v1"),
    ]
  }
}
