import Foundation

public enum NativeCapability: String, Codable, CaseIterable, Sendable {
  case contactsStatus = "contacts.status"
  case contactsSearch = "contacts.search"
  case contactsGet = "contacts.get"
  case contactsListLimited = "contacts.list_limited"
  case calendarStatus = "calendar.status"
  case calendarCalendarsList = "calendar.calendars.list"
  case calendarEventsRange = "calendar.events.range"
  case calendarEventsGet = "calendar.events.get"
  case calendarEventsCreate = "calendar.events.create"
  case mailAccountsList = "mail.accounts.list"
  case mailMailboxesList = "mail.mailboxes.list"
  case mailMessagesList = "mail.messages.list"
  case mailDraftCreate = "mail.draft.create"
  case wakewordStatus = "wakeword.status"
  case wakewordStart = "wakeword.start"
  case wakewordStop = "wakeword.stop"
}

public enum NativeCapabilityOrigin: String, Codable, Sendable { case localCore }
public let nativeCapabilityProtocolVersion = "native-capability-broker-v1"

public enum BrokerJSONValue: Codable, Equatable, Sendable {
  case string(String)
  case number(Double)
  case boolean(Bool)
  case object([String: BrokerJSONValue])
  case array([BrokerJSONValue])
  case null
  public init(from decoder: Decoder) throws {
    if let value = try? decoder.singleValueContainer().decode(String.self) {
      self = .string(value)
      return
    }
    if let value = try? decoder.singleValueContainer().decode(Bool.self) {
      self = .boolean(value)
      return
    }
    if let value = try? decoder.singleValueContainer().decode(Double.self), value.isFinite {
      self = .number(value)
      return
    }
    if let value = try? decoder.singleValueContainer().decode([String: BrokerJSONValue].self) {
      self = .object(value)
      return
    }
    if let value = try? decoder.singleValueContainer().decode([BrokerJSONValue].self) {
      self = .array(value)
      return
    }
    if try decoder.singleValueContainer().decodeNil() {
      self = .null
      return
    }
    throw BrokerError.invalidRequest
  }
  public func encode(to encoder: Encoder) throws {
    var container = encoder.singleValueContainer()
    switch self {
    case .string(let v): try container.encode(v)
    case .number(let v):
      guard v.isFinite else { throw BrokerError.invalidRequest }
      try container.encode(v)
    case .boolean(let v): try container.encode(v)
    case .object(let v): try container.encode(v)
    case .array(let v): try container.encode(v)
    case .null: try container.encodeNil()
    }
  }
  public func validate(depth: Int = 0) throws {
    guard depth <= 6 else { throw BrokerError.invalidArguments }
    switch self {
    case .string(let v): guard v.count <= 4_000 else { throw BrokerError.invalidArguments }
    case .number(let v): guard v.isFinite else { throw BrokerError.invalidArguments }
    case .object(let v):
      guard v.count <= 32 else { throw BrokerError.invalidArguments }
      try v.values.forEach { try $0.validate(depth: depth + 1) }
    case .array(let v):
      guard v.count <= 32 else { throw BrokerError.invalidArguments }
      try v.forEach { try $0.validate(depth: depth + 1) }
    default: break
    }
  }
}

public struct NativeCapabilityRequest: Codable, Equatable, Sendable {
  public let protocolVersion: String
  public let requestId: String
  public let capability: NativeCapability
  public let requesterId: String
  public let origin: NativeCapabilityOrigin
  public let explicitUserRequest: Bool
  public let requestLocale: String
  public let responseLocale: String
  public let createdAt: Date
  public let arguments: [String: BrokerJSONValue]
  public init(
    protocolVersion: String = nativeCapabilityProtocolVersion, requestId: String,
    capability: NativeCapability, requesterId: String, origin: NativeCapabilityOrigin = .localCore,
    explicitUserRequest: Bool, requestLocale: String, responseLocale: String,
    createdAt: Date = Date(), arguments: [String: BrokerJSONValue]
  ) throws {
    self.protocolVersion = protocolVersion
    self.requestId = requestId
    self.capability = capability
    self.requesterId = requesterId
    self.origin = origin
    self.explicitUserRequest = explicitUserRequest
    self.requestLocale = requestLocale
    self.responseLocale = responseLocale
    self.createdAt = createdAt
    self.arguments = arguments
    try validate()
  }
  private enum CodingKeys: String, CodingKey {
    case protocolVersion, requestId, capability, requesterId, origin, explicitUserRequest,
      requestLocale, responseLocale, createdAt, arguments
  }
  public init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    self.protocolVersion = try c.decode(String.self, forKey: .protocolVersion)
    self.requestId = try c.decode(String.self, forKey: .requestId)
    self.capability = try c.decode(NativeCapability.self, forKey: .capability)
    self.requesterId = try c.decode(String.self, forKey: .requesterId)
    self.origin = try c.decode(NativeCapabilityOrigin.self, forKey: .origin)
    self.explicitUserRequest = try c.decode(Bool.self, forKey: .explicitUserRequest)
    self.requestLocale = try c.decode(String.self, forKey: .requestLocale)
    self.responseLocale = try c.decode(String.self, forKey: .responseLocale)
    guard
      let date = ISO8601DateFormatter.broker.date(
        from: try c.decode(String.self, forKey: .createdAt))
    else { throw BrokerError.invalidRequest }
    self.createdAt = date
    self.arguments = try c.decode([String: BrokerJSONValue].self, forKey: .arguments)
    try validate()
  }
  public func encode(to encoder: Encoder) throws {
    var c = encoder.container(keyedBy: CodingKeys.self)
    try c.encode(protocolVersion, forKey: .protocolVersion)
    try c.encode(requestId, forKey: .requestId)
    try c.encode(capability, forKey: .capability)
    try c.encode(requesterId, forKey: .requesterId)
    try c.encode(origin, forKey: .origin)
    try c.encode(explicitUserRequest, forKey: .explicitUserRequest)
    try c.encode(requestLocale, forKey: .requestLocale)
    try c.encode(responseLocale, forKey: .responseLocale)
    try c.encode(ISO8601DateFormatter.broker.string(from: createdAt), forKey: .createdAt)
    try c.encode(arguments, forKey: .arguments)
  }
  public func validate() throws {
    guard protocolVersion == nativeCapabilityProtocolVersion else {
      throw BrokerError.unsupportedProtocol
    }
    guard validMachineID(requestId), validMachineID(requesterId) else {
      throw BrokerError.invalidRequest
    }
    guard validLocale(requestLocale), validLocale(responseLocale) else {
      throw BrokerError.invalidRequest
    }
    guard arguments.count <= 32 else { throw BrokerError.invalidArguments }
    try arguments.values.forEach { try $0.validate() }
  }
}

public struct NativeCapabilityProvenance: Equatable, Sendable {
  public let requesterId: String
  public let origin: NativeCapabilityOrigin
  public let protocolVersion: String
  public let requestId: String
}
public enum BrokerOutcome: String, Codable, Sendable {
  case success, rejected, unavailable, notImplemented, failed
}
public struct BrokerError: Error, Codable, Equatable, Sendable {
  public let code: String
  public init(_ code: String) { self.code = code }
  public static let invalidRequest = BrokerError("invalid_request")
  public static let unsupportedProtocol = BrokerError("unsupported_protocol")
  public static let capabilityNotAllowed = BrokerError("capability_not_allowed")
  public static let invalidArguments = BrokerError("invalid_arguments")
  public static let permissionNotRequested = BrokerError("permission_not_requested")
  public static let permissionDenied = BrokerError("permission_denied")
  public static let permissionRestricted = BrokerError("permission_restricted")
  public static let capabilityUnavailable = BrokerError("capability_unavailable")
  public static let notImplemented = BrokerError("not_implemented")
  public static let internalFailure = BrokerError("internal_failure")
  public static let contactReferenceUnknown = BrokerError("contact_reference_unknown")
  public static let eventReferenceUnknown = BrokerError("event_reference_unknown")
  public static let calendarReferenceUnknown = BrokerError("calendar_reference_unknown")
  public static let mailAccountReferenceUnknown = BrokerError("mail_account_reference_unknown")
  public static let mailMailboxReferenceUnknown = BrokerError("mail_mailbox_reference_unknown")
  public static let calendarNotModifiable = BrokerError("calendar_not_modifiable")
}
public struct NativeCapabilityResponse: Codable, Equatable, Sendable {
  public let protocolVersion: String
  public let requestId: String
  public let capability: NativeCapability
  public let outcome: BrokerOutcome
  public let result: [String: BrokerJSONValue]?
  public let error: BrokerError?
  public let limitations: [String]
  public let method: String
}

private func validMachineID(_ value: String) -> Bool {
  value.count <= 64 && !value.isEmpty
    && value.unicodeScalars.allSatisfy {
      ($0.value >= 97 && $0.value <= 122) || ($0.value >= 48 && $0.value <= 57) || $0 == "-"
        || $0 == "_" || $0 == "."
    }
}
private func validLocale(_ value: String) -> Bool {
  let base = value.split(separator: "-").first.map(String.init) ?? ""
  return ["en", "es", "fi", "sv"].contains(base) && value.count <= 16
}

extension ISO8601DateFormatter {
  fileprivate static let broker: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
  }()
}
