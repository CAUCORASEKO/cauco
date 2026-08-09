import EventKit
import Foundation

public protocol CalendarDataGateway: Sendable {
  func list(limit: Int) throws -> [String: BrokerJSONValue]
  func eventsRange(start: String, end: String, limit: Int, calendarReference: String?) throws -> [String: BrokerJSONValue]
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
  public func identifier(for reference: String) -> String? { lock.lock(); defer { lock.unlock() }; return byReference[reference] }
}

public final class EventReferenceRegistry: @unchecked Sendable {
  private let lock = NSLock(); private let capacity: Int
  private var byIdentifier: [String: String] = [:]; private var order: [String] = []
  public init(capacity: Int = 1000) { self.capacity = max(1, capacity) }
  public func reference(for identifier: String) -> String {
    lock.lock(); defer { lock.unlock() }
    if let value = byIdentifier[identifier] { return value }
    let value = "event_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
    byIdentifier[identifier] = value; order.append(identifier)
    while order.count > capacity { byIdentifier.removeValue(forKey: order.removeFirst()) }
    return value
  }
}

public final class NativeCalendarDataGateway: CalendarDataGateway, @unchecked Sendable {
  private let store: EKEventStore; private let permission: CalendarPermissionGateway; private let references: CalendarReferenceRegistry
  private let eventReferences: EventReferenceRegistry
  public init(store: EKEventStore = EKEventStore(), permission: CalendarPermissionGateway,
              references: CalendarReferenceRegistry = CalendarReferenceRegistry(), eventReferences: EventReferenceRegistry = EventReferenceRegistry()) { self.store = store; self.permission = permission; self.references = references; self.eventReferences = eventReferences }
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
  public func eventsRange(start: String, end: String, limit: Int, calendarReference: String?) throws -> [String: BrokerJSONValue] {
    guard (1...100).contains(limit) else { throw BrokerError.invalidArguments }
    switch permission.authorizationState() { case .granted: break; case .notRequested: throw BrokerError.permissionNotRequested; case .denied: throw BrokerError.permissionDenied; case .restricted: throw BrokerError.permissionRestricted; case .unavailable: throw BrokerError.capabilityUnavailable }
    guard let startDate = calendarISO8601Date(start), let endDate = calendarISO8601Date(end), startDate < endDate, endDate.timeIntervalSince(startDate) <= 31 * 86400 else { throw BrokerError.invalidArguments }
    let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let selected: [EKCalendar]?
    if let calendarReference { guard let identifier = references.identifier(for: calendarReference), let calendar = store.calendar(withIdentifier: identifier) else { throw BrokerError.invalidArguments }; selected = [calendar] } else { selected = nil }
    let events = store.events(matching: store.predicateForEvents(withStart: startDate, end: endDate, calendars: selected))
    let values = events.compactMap { event -> (String, BrokerJSONValue)? in
      guard let calendar = event.calendar else { return nil }; let calendarReference = references.reference(for: calendar.calendarIdentifier); let eventReference = eventReferences.reference(for: event.eventIdentifier)
      let startText = formatter.string(from: event.startDate), endText = formatter.string(from: event.endDate)
      return (startText + "\u{0}" + endText + "\u{0}" + calendarSanitized(event.title ?? "", limit: 300).lowercased() + "\u{0}" + eventReference, .object(["event_reference": .string(eventReference), "calendar_reference": .string(calendarReference), "title": .string(calendarSanitized(event.title ?? "", limit: 300)), "start": .string(startText), "end": .string(endText), "all_day": .boolean(event.isAllDay), "location": .string(calendarSanitized(event.location ?? "", limit: 300)), "notes": .string(calendarSanitized(event.notes ?? "", limit: 1000))]))
    }.sorted { $0.0 < $1.0 }
    let results = values.prefix(limit).map { $0.1 }
    return ["results": .array(results), "result_count": .number(Double(results.count)), "truncated": .boolean(values.count > limit), "range_start": .string(start), "range_end": .string(end)]
  }
}

func calendarISO8601Date(_ value: String) -> Date? {
  for options: ISO8601DateFormatter.Options in [[.withInternetDateTime, .withFractionalSeconds], [.withInternetDateTime]] {
    let formatter = ISO8601DateFormatter(); formatter.formatOptions = options
    if let date = formatter.date(from: value) { return date }
  }
  return nil
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
