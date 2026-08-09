import Foundation

public final class NativeCapabilityBroker: @unchecked Sendable {
  private let permission: ContactsPermissionGateway
  private let contacts: ContactsDataGateway
  private let calendarPermission: CalendarPermissionGateway
  private let calendars: CalendarDataGateway
  public let registry: NativeCapabilityRegistry
  public init(
    permission: ContactsPermissionGateway,
    calendarPermission: CalendarPermissionGateway = NativeCalendarPermissionGateway(),
    contacts: ContactsDataGateway? = nil,
    calendars: CalendarDataGateway? = nil,
    registry: NativeCapabilityRegistry = NativeCapabilityRegistry()
  ) {
    self.permission = permission
    self.contacts = contacts ?? NativeContactsDataGateway(permission: permission)
    self.calendarPermission = calendarPermission
    self.calendars = calendars ?? NativeCalendarDataGateway(permission: calendarPermission)
    self.registry = registry
  }
  public func handle(_ request: NativeCapabilityRequest) -> NativeCapabilityResponse {
    do { try request.validate() } catch let error as BrokerError {
      return response(request, .rejected, nil, error, [])
    } catch { return response(request, .rejected, nil, .invalidRequest, []) }
    guard
      let definition = registry.definitions.first(where: { $0.capability == request.capability })
    else { return response(request, .rejected, nil, .capabilityNotAllowed, []) }
    do { try validateArguments(request.arguments, for: request.capability) } catch {
      return response(request, .rejected, nil, .invalidArguments, definition.limitations)
    }
    switch request.capability {
    case .contactsStatus: return status(request, definition)
    case .calendarStatus: return calendarStatus(request, definition)
    case .calendarEventsGet:
      do { return response(request, .success, try calendars.eventGet(reference: request.arguments["event_reference"]!.stringValue!), nil, definition.limitations) }
      catch let error as BrokerError { return response(request, .rejected, nil, error, definition.limitations) }
      catch { return response(request, .failed, nil, .internalFailure, definition.limitations) }
    case .calendarEventsCreate:
      do { let a = request.arguments; return response(request, .success, try calendars.eventCreate(title: a["title"]!.stringValue!, start: a["start"]!.stringValue!, end: a["end"]!.stringValue!, allDay: a["all_day"]!.boolValue!, calendarReference: a["calendar_reference"]?.stringValue, location: a["location"]?.stringValue, notes: a["notes"]?.stringValue), nil, definition.limitations) }
      catch let error as BrokerError { return response(request, .rejected, nil, error, definition.limitations) }
      catch { return response(request, .failed, nil, .internalFailure, definition.limitations) }
    case .calendarCalendarsList:
      do { return response(request, .success, try calendars.list(limit: Int(request.arguments["limit"]!.numberValue!)), nil, definition.limitations) }
      catch let error as BrokerError { return response(request, .rejected, nil, error, definition.limitations) }
      catch { return response(request, .failed, nil, .internalFailure, definition.limitations) }
    case .calendarEventsRange:
      do { let start = request.arguments["start"]!.stringValue!, end = request.arguments["end"]!.stringValue!, limit = Int(request.arguments["limit"]!.numberValue!), ref = request.arguments["calendar_reference"]?.stringValue; return response(request, .success, try calendars.eventsRange(start: start, end: end, limit: limit, calendarReference: ref), nil, definition.limitations) }
      catch let error as BrokerError { return response(request, .rejected, nil, error, definition.limitations) }
      catch { return response(request, .failed, nil, .internalFailure, definition.limitations) }
    case .contactsSearch:
      guard
        case let .string(query)? = request.arguments["query"],
        !query.isEmpty,
        case let .number(rawLimit)? = request.arguments["limit"],
        rawLimit.isFinite,
        rawLimit.rounded() == rawLimit,
        (1...20).contains(rawLimit)
      else {
        return response(request, .rejected, nil, .invalidArguments, definition.limitations)
      }
      do {
        let limit = Swift.Int(rawLimit)
        return response(request, .success, try contacts.search(query: query, limit: limit), nil, definition.limitations)
      } catch let error as BrokerError { return response(request, .rejected, nil, error, definition.limitations) }
      catch { return response(request, .failed, nil, .internalFailure, definition.limitations) }
    case .contactsGet:
      guard case let .string(reference)? = request.arguments["contactRef"] else {
        return response(request, .rejected, nil, .invalidArguments, definition.limitations)
      }
      do {
        return response(request, .success, try contacts.get(contactReference: reference), nil, definition.limitations)
      } catch let error as BrokerError {
        return response(request, .rejected, nil, error, definition.limitations)
      } catch {
        return response(request, .failed, nil, .internalFailure, definition.limitations)
      }
    case .contactsListLimited:
      guard case let .number(rawLimit)? = request.arguments["limit"], rawLimit.isFinite,
        rawLimit.rounded() == rawLimit, (1...20).contains(rawLimit) else {
        return response(request, .rejected, nil, .invalidArguments, definition.limitations)
      }
      do {
        return response(request, .success,
          try contacts.listLimited(limit: Swift.Int(rawLimit)), nil, definition.limitations)
      } catch let error as BrokerError {
        return response(request, .rejected, nil, error, definition.limitations)
      } catch {
        return response(request, .failed, nil, .internalFailure, definition.limitations)
      }
    }
  }
  private func status(_ request: NativeCapabilityRequest, _ definition: NativeCapabilityDefinition)
    -> NativeCapabilityResponse
  {
    let state: (String, Bool) = {
      switch permission.authorizationState() {
      case .notRequested: return ("notRequested", false)
      case .granted: return ("granted", true)
      case .denied: return ("denied", false)
      case .restricted: return ("restricted", false)
      case .unavailable: return ("unavailable", false)
      }
    }()
    return response(
      request, .success,
      [
        "permissionId": .string(definition.permissionId), "state": .string(state.0),
        "available": .boolean(state.1),
      ], nil, definition.limitations)
  }
  private func response(
    _ request: NativeCapabilityRequest, _ outcome: BrokerOutcome,
    _ result: [String: BrokerJSONValue]?, _ error: BrokerError?, _ limitations: [String]
  ) -> NativeCapabilityResponse {
    NativeCapabilityResponse(
      protocolVersion: nativeCapabilityProtocolVersion, requestId: request.requestId,
      capability: request.capability, outcome: outcome, result: result, error: error,
      limitations: limitations,
      method: registry.definitions.first(where: { $0.capability == request.capability })?.method
        ?? "unknown")
  }
  private func validateArguments(
    _ args: [String: BrokerJSONValue], for capability: NativeCapability
  ) throws {
    switch capability {
    case .contactsStatus, .calendarStatus: guard args.isEmpty else { throw BrokerError.invalidArguments }
    case .contactsSearch:
      guard Set(args.keys) == Set(["query", "limit"]), caseString(args["query"])?.isEmpty == false,
        caseInt(args["limit"]) != nil
      else { throw BrokerError.invalidArguments }
    case .contactsGet:
      guard Set(args.keys) == Set(["contactRef"]), caseString(args["contactRef"])?.isEmpty == false
      else { throw BrokerError.invalidArguments }
    case .contactsListLimited:
      guard Set(args.keys) == Set(["limit"]), caseInt(args["limit"]) != nil else {
        throw BrokerError.invalidArguments
      }
    case .calendarCalendarsList:
      guard Set(args.keys) == Set(["limit"]), caseInt(args["limit"], max: 50) != nil else { throw BrokerError.invalidArguments }
    case .calendarEventsRange:
      guard Set(args.keys).isSubset(of: ["start", "end", "limit", "calendar_reference"]), caseString(args["start"]) != nil, caseString(args["end"]) != nil, caseInt(args["limit"], max: 100) != nil, args.keys.contains("start"), args.keys.contains("end"), args.keys.contains("limit") else { throw BrokerError.invalidArguments }
      if let reference = args["calendar_reference"], caseString(reference) == nil { throw BrokerError.invalidArguments }
    case .calendarEventsGet:
      guard Set(args.keys) == Set(["event_reference"]), caseString(args["event_reference"]) != nil, args["event_reference"]!.stringValue!.range(of: #"^event_[A-Za-z0-9_-]{8,80}$"#, options: .regularExpression) != nil else { throw BrokerError.invalidArguments }
    case .calendarEventsCreate:
      let allowed = Set(["title", "start", "end", "all_day", "calendar_reference", "location", "notes"])
      guard Set(args.keys).isSubset(of: allowed), Set(["title", "start", "end", "all_day"]).isSubset(of: Set(args.keys)), caseString(args["title"])?.isEmpty == false, caseString(args["start"]) != nil, caseString(args["end"]) != nil, args["all_day"]!.boolValue != nil else { throw BrokerError.invalidArguments }
      for key in ["location", "notes", "calendar_reference"] { if let value = args[key], caseString(value) == nil { throw BrokerError.invalidArguments } }
    }
  }
  private func calendarStatus(_ request: NativeCapabilityRequest, _ definition: NativeCapabilityDefinition) -> NativeCapabilityResponse {
    let state: (String, Bool) = {
      switch calendarPermission.authorizationState() {
      case .notRequested: return ("notRequested", false)
      case .granted: return ("granted", true)
      case .denied: return ("denied", false)
      case .restricted: return ("restricted", false)
      case .unavailable: return ("unavailable", false)
      }
    }()
    return response(request, .success, ["permissionId": .string(definition.permissionId), "state": .string(state.0), "available": .boolean(state.1)], nil, definition.limitations)
  }
  private func caseString(_ value: BrokerJSONValue?) -> String? {
    if case .string(let value) = value { return value.count <= 256 ? value : nil }
    return nil
  }
  private func caseInt(_ value: BrokerJSONValue?, max: Double = 20) -> Int? {
    if case .number(let value) = value, value.rounded() == value, value >= 1, value <= max {
      return Int(value)
    }
    return nil
  }
}

private extension BrokerJSONValue { var numberValue: Double? { if case .number(let value) = self { return value }; return nil } }
private extension BrokerJSONValue { var stringValue: String? { if case .string(let value) = self { return value }; return nil } }
private extension BrokerJSONValue { var boolValue: Bool? { if case .boolean(let value) = self { return value }; return nil } }
