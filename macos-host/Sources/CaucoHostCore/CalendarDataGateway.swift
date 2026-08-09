import EventKit
import Foundation

public protocol CalendarDataGateway: Sendable {
  func list(limit: Int) throws -> [String: BrokerJSONValue]
}

public final class CalendarReferenceRegistry: @unchecked Sendable {
  private let lock = NSLock(); private let capacity: Int
  private var byReference: [String: String] = [:]; private var byIdentifier: [String: String] = [:]; private var order: [String] = []
  public init(capacity: Int = 200) { self.capacity = max(1, capacity) }
  public func reference(for identifier: String) -> String {
    lock.lock(); defer { lock.unlock() }
    if let value = byIdentifier[identifier] { return value }
    let value = "calendar_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
    byReference[value] = identifier; byIdentifier[identifier] = value; order.append(value)
    while order.count > capacity { let old = order.removeFirst(); if let id = byReference.removeValue(forKey: old) { byIdentifier.removeValue(forKey: id) } }
    return value
  }
}

public final class NativeCalendarDataGateway: CalendarDataGateway, @unchecked Sendable {
  private let store: EKEventStore; private let permission: CalendarPermissionGateway; private let references: CalendarReferenceRegistry
  public init(store: EKEventStore = EKEventStore(), permission: CalendarPermissionGateway,
              references: CalendarReferenceRegistry = CalendarReferenceRegistry()) { self.store = store; self.permission = permission; self.references = references }
  public func list(limit: Int) throws -> [String: BrokerJSONValue] {
    guard (1...50).contains(limit) else { throw BrokerError.invalidArguments }
    switch permission.authorizationState() {
    case .granted: break
    case .notRequested: throw BrokerError.permissionNotRequested
    case .denied: throw BrokerError.permissionDenied
    case .restricted: throw BrokerError.permissionRestricted
    case .unavailable: throw BrokerError.capabilityUnavailable
    }
    let values = store.calendars(for: .event).compactMap { calendar -> (String, BrokerJSONValue)? in
      let reference = references.reference(for: calendar.calendarIdentifier)
      let title = calendarSanitized(calendar.title, limit: 200), source = calendarSanitized(calendar.source?.title ?? "", limit: 200)
      let type: String = {
        switch calendar.type { case .local: return "local"; case .calDAV: return "caldav"; case .exchange: return "exchange"; case .subscription: return "subscription"; case .birthday: return "birthday"; @unknown default: return "unknown" }
      }()
      return (title.lowercased() + "\u{0}" + source.lowercased() + "\u{0}" + reference,
        .object(["calendar_reference": .string(reference), "title": .string(title), "source_title": .string(source), "type": .string(type), "allows_content_modifications": .boolean(calendar.allowsContentModifications)]))
    }.sorted { $0.0 < $1.0 }
    let selected = values.prefix(limit).map { $0.1 }
    return ["results": .array(selected), "result_count": .number(Double(selected.count)), "truncated": .boolean(values.count > limit)]
  }
}

// Keep normal Unicode intact while removing C0/C1 controls without relying on
// Foundation CharacterSet or newer Unicode.Scalar APIs.
func calendarSanitized(_ value: String, limit: Int) -> String {
  guard limit > 0 else { return "" }
  return String(value.unicodeScalars.filter { scalar in
    let code = scalar.value
    return !(code <= 0x1F || (0x7F...0x9F).contains(code))
  }.prefix(limit))
}
