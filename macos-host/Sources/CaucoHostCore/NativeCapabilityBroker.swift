import Foundation

public final class NativeCapabilityBroker: @unchecked Sendable {
  private let permission: ContactsPermissionGateway
  private let contacts: ContactsDataGateway
  private let calendarPermission: CalendarPermissionGateway
  private let calendars: CalendarDataGateway
  private let mailAccounts: MailAccountGateway
  private let mailMessages: MailMessageGateway
  private let mailDrafts: MailDraftGateway
  private let wakeWord: WakeWordCapabilityService
  public let registry: NativeCapabilityRegistry

  public init(
    permission: ContactsPermissionGateway,
    calendarPermission: CalendarPermissionGateway = NativeCalendarPermissionGateway(),
    contacts: ContactsDataGateway? = nil,
    calendars: CalendarDataGateway? = nil,
    mailAccounts: MailAccountGateway? = nil,
    mailMessages: MailMessageGateway? = nil,
    mailDrafts: MailDraftGateway? = nil,
    wakeWordDetector: WakeWordDetectorGateway = UnavailableWakeWordDetectorGateway(),
    wakeWordEventHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void = { _ in },
    registry: NativeCapabilityRegistry = NativeCapabilityRegistry()
  ) {
    self.permission = permission
    self.contacts = contacts ?? NativeContactsDataGateway(permission: permission)
    self.calendarPermission = calendarPermission
    self.calendars = calendars ?? NativeCalendarDataGateway(permission: calendarPermission)
    let mailReferences = MailAccountReferenceRegistry()
    self.mailAccounts = mailAccounts ?? NativeMailAccountGateway(references: mailReferences)
    self.mailMessages = mailMessages ?? NativeMailMessageGateway(
      accountReferences: mailReferences)
    self.mailDrafts = mailDrafts ?? NativeMailDraftGateway()
    self.wakeWord = WakeWordCapabilityService(
      detector: wakeWordDetector, eventHandler: wakeWordEventHandler)
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
    case .wakewordStatus:
      return response(
        request, .success, wakeWord.status().brokerResult, nil, definition.limitations)
    case .wakewordStart:
      guard request.explicitUserRequest else {
        return response(
          request, .rejected, nil, .permissionNotRequested, definition.limitations)
      }
      do {
        let configuration = WakeWordDetectorConfiguration(
          phraseKey: request.arguments["phrase_key"]!.stringValue!,
          locale: request.arguments["locale"]!.stringValue!)
        var result = try wakeWord.start(configuration: configuration).brokerResult
        result["accepted"] = .boolean(true)
        return response(
          request, .success, result, nil, definition.limitations)
      } catch let error as BrokerError {
        let outcome: BrokerOutcome = error == .capabilityUnavailable ? .unavailable : .rejected
        var result = wakeWord.status().brokerResult
        result["accepted"] = .boolean(false)
        return response(
          request, outcome, result, error, definition.limitations)
      } catch {
        return response(
          request, .failed, wakeWord.status().brokerResult, .internalFailure,
          definition.limitations)
      }
    case .wakewordStop:
      return response(
        request, .success, wakeWord.stop().brokerResult, nil, definition.limitations)
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
    case .mailAccountsList:
      do {
        return response(
          request, .success, try mailAccounts.listAccounts(), nil, definition.limitations)
      } catch let error as BrokerError {
        return response(request, .rejected, nil, error, definition.limitations)
      } catch {
        return response(request, .failed, nil, .internalFailure, definition.limitations)
      }
    case .mailMailboxesList:
      do {
        return response(
          request, .success,
          try mailAccounts.listMailboxes(
            accountReference: request.arguments["account_reference"]!.stringValue!),
          nil, definition.limitations)
      } catch let error as BrokerError {
        return response(request, .rejected, nil, error, definition.limitations)
      } catch {
        return response(request, .failed, nil, .internalFailure, definition.limitations)
      }
    case .mailMessagesList:
      do {
        let limit = Int(request.arguments["limit"]!.numberValue!)
        return response(
          request,
          .success,
          try mailMessages.listMessages(
            mailboxReference: request.arguments["mailbox_reference"]!.stringValue!, limit: limit),
          nil,
          definition.limitations
        )
      } catch let error as BrokerError {
        return response(
          request,
          .rejected,
          nil,
          error,
          definition.limitations
        )
      } catch {
        return response(
          request,
          .failed,
          nil,
          .internalFailure,
          definition.limitations
        )
      }
    case .mailDraftCreate:
      do {
        let arguments = request.arguments
        return response(
          request,
          .success,
          try mailDrafts.createDraft(
            recipient: arguments["recipient"]!.stringValue!,
            subject: arguments["subject"]!.stringValue!,
            body: arguments["body"]!.stringValue!
          ),
          nil,
          definition.limitations
        )
      } catch let error as BrokerError {
        return response(request, .rejected, nil, error, definition.limitations)
      } catch {
        return response(request, .failed, nil, .internalFailure, definition.limitations)
      }
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

  public func shutdown() {
    wakeWord.stop()
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
    case .contactsStatus, .calendarStatus, .mailAccountsList, .wakewordStatus, .wakewordStop:
      guard args.isEmpty else { throw BrokerError.invalidArguments }
    case .wakewordStart:
      guard Set(args.keys) == Set(["phrase_key", "locale"]),
        caseString(args["phrase_key"]) == "hola_cauco",
        let locale = caseString(args["locale"]),
        validWakeWordLocale(locale)
      else { throw BrokerError.invalidArguments }
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
    case .mailMessagesList:
      guard Set(args.keys) == Set(["mailbox_reference", "limit"]),
        let reference = caseString(args["mailbox_reference"]),
        reference.range(of: #"^mailbox_[A-Za-z0-9_-]{8,80}$"#, options: .regularExpression)
          != nil,
        caseInt(args["limit"], max: 20) != nil
      else {
        throw BrokerError.invalidArguments
      }
    case .mailMailboxesList:
      guard Set(args.keys) == Set(["account_reference"]),
        let reference = caseString(args["account_reference"]),
        reference.range(of: #"^mailacct_[A-Za-z0-9_-]{8,80}$"#, options: .regularExpression)
          != nil
      else {
        throw BrokerError.invalidArguments
      }
    case .mailDraftCreate:
      guard Set(args.keys) == Set(["recipient", "subject", "body"]),
        let recipient = caseString(args["recipient"]),
        !recipient.isEmpty,
        let subject = caseString(args["subject"]),
        !subject.isEmpty,
        caseBoundedString(args["body"], max: 4_000) != nil
      else {
        throw BrokerError.invalidArguments
      }
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
  private func caseBoundedString(
    _ value: BrokerJSONValue?, max: Int
  ) -> String? {
    guard max > 0 else { return nil }
    if case .string(let value) = value, value.count <= max {
      return value
    }
    return nil
  }

  private func caseInt(_ value: BrokerJSONValue?, max: Double = 20) -> Int? {
    if case .number(let value) = value, value.rounded() == value, value >= 1, value <= max {
      return Int(value)
    }
    return nil
  }

  private func validWakeWordLocale(_ locale: String) -> Bool {
    locale.range(of: #"^es(?:-[A-Z]{2})?$"#, options: .regularExpression) != nil
  }
}

private extension BrokerJSONValue { var numberValue: Double? { if case .number(let value) = self { return value }; return nil } }
private extension BrokerJSONValue { var stringValue: String? { if case .string(let value) = self { return value }; return nil } }
private extension BrokerJSONValue { var boolValue: Bool? { if case .boolean(let value) = self { return value }; return nil } }
