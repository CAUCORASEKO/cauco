import Foundation

public final class NativeCapabilityBroker: @unchecked Sendable {
  private let permission: ContactsPermissionGateway
  public let registry: NativeCapabilityRegistry
  public init(
    permission: ContactsPermissionGateway,
    registry: NativeCapabilityRegistry = NativeCapabilityRegistry()
  ) {
    self.permission = permission
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
    case .contactsSearch, .contactsGet, .contactsListLimited:
      return response(request, .notImplemented, nil, .notImplemented, definition.limitations)
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
    case .contactsStatus: guard args.isEmpty else { throw BrokerError.invalidArguments }
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
    }
  }
  private func caseString(_ value: BrokerJSONValue?) -> String? {
    if case .string(let value) = value { return value.count <= 256 ? value : nil }
    return nil
  }
  private func caseInt(_ value: BrokerJSONValue?) -> Int? {
    if case .number(let value) = value, value.rounded() == value, value >= 1, value <= 20 {
      return Int(value)
    }
    return nil
  }
}
