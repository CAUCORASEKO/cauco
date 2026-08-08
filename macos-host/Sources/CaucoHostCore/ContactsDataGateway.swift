import Contacts
import CryptoKit
import Foundation

public protocol ContactsDataGateway: Sendable {
  func search(query: String, limit: Int) throws -> [String: BrokerJSONValue]
  func get(contactReference: String) throws -> [String: BrokerJSONValue]
}

public final class ContactsReferenceRegistry: @unchecked Sendable {
  private let lock = NSLock()
  private let capacity: Int
  private var references: [String: String] = [:]
  private var order: [String] = []
  public init(capacity: Int = 500) { self.capacity = max(1, capacity) }
  public func register(reference: String, identifier: String) {
    guard !reference.isEmpty, !identifier.isEmpty else { return }
    lock.lock(); defer { lock.unlock() }
    if references[reference] == nil { order.append(reference) }
    references[reference] = identifier
    while order.count > capacity { references.removeValue(forKey: order.removeFirst()) }
  }
  public func identifier(for reference: String) -> String? {
    lock.lock(); defer { lock.unlock() }
    return references[reference]
  }
  public var count: Int { lock.lock(); defer { lock.unlock() }; return references.count }
}

/// Read-only, bounded Contacts gateway. The supported query is Contacts' name predicate;
/// this deliberately avoids enumerating the address book for cross-field matching.
public final class NativeContactsDataGateway: ContactsDataGateway, @unchecked Sendable {
  private let store: CNContactStore
  private let permission: ContactsPermissionGateway
  private let secret = Data(UUID().uuidString.utf8)
  private let references: ContactsReferenceRegistry

  public init(store: CNContactStore = CNContactStore(), permission: ContactsPermissionGateway,
              references: ContactsReferenceRegistry = ContactsReferenceRegistry()) {
    self.store = store
    self.permission = permission
    self.references = references
  }

  public func search(query: String, limit: Int) throws -> [String: BrokerJSONValue] {
    guard !query.isEmpty, query.count <= 200, (1...20).contains(limit) else {
      throw BrokerError.invalidArguments
    }
    switch permission.authorizationState() {
    case .notRequested: throw BrokerError.permissionNotRequested
    case .denied: throw BrokerError.permissionDenied
    case .restricted: throw BrokerError.permissionRestricted
    case .unavailable: throw BrokerError.capabilityUnavailable
    case .granted: break
    }
    let requestedKeys: [CNKeyDescriptor] = [
      CNContactIdentifierKey as CNKeyDescriptor,
      CNContactGivenNameKey as CNKeyDescriptor,
      CNContactFamilyNameKey as CNKeyDescriptor,
      CNContactOrganizationNameKey as CNKeyDescriptor,
      CNContactEmailAddressesKey as CNKeyDescriptor,
      CNContactPhoneNumbersKey as CNKeyDescriptor,
    ]
    let request = CNContactFetchRequest(keysToFetch: requestedKeys)
    request.predicate = CNContact.predicateForContacts(matchingName: query)
    var contacts: [CNContact] = []
    try store.enumerateContacts(with: request) { contact, stop in
      contacts.append(contact)
      if contacts.count >= limit {
        stop.pointee = true
      }
    }

    struct ContactResult {
      let sortKey: (String, String, String)
      let value: BrokerJSONValue
    }

    let values = contacts.compactMap { contact -> ContactResult? in
      guard !contact.identifier.isEmpty else {
        return nil
      }
      guard let reference = opaqueReference(for: contact.identifier) else {
        return nil
      }
      references.register(reference: reference, identifier: contact.identifier)
      let given = contact.givenName
      let family = contact.familyName
      let organization = contact.organizationName
      let displayName = [given, family].filter { !$0.isEmpty }.joined(separator: " ")
      let visibleName = displayName.isEmpty ? organization : displayName
      let emails = contact.emailAddresses.prefix(10).map { address in
        BrokerJSONValue.object([
          "label": sanitized(normalizeContactLabel(address.label), limit: 50),
          "address": sanitized(String(address.value), limit: 254),
        ])
      }
      let phones = contact.phoneNumbers.prefix(10).map { labeledValue in
        let number = labeledValue.value.stringValue
        let normalized = number.filter { $0.isNumber || $0 == "+" }
        return BrokerJSONValue.object([
          "label": sanitized(normalizeContactLabel(labeledValue.label), limit: 50),
          "number": sanitized(number, limit: 80),
          "normalized_number": sanitized(normalized, limit: 80),
        ])
      }
      return ContactResult(
        sortKey: (visibleName.lowercased(), organization.lowercased(), reference),
        value: .object([
          "contact_reference": .string(reference),
          "display_name": sanitized(visibleName, limit: 200),
          "given_name": sanitized(given, limit: 200),
          "family_name": sanitized(family, limit: 200),
          "organization": sanitized(organization, limit: 200),
          "emails": .array(emails),
          "phones": .array(phones),
        ]))
    }.sorted {
      if $0.sortKey.0 != $1.sortKey.0 { return $0.sortKey.0 < $1.sortKey.0 }
      if $0.sortKey.1 != $1.sortKey.1 { return $0.sortKey.1 < $1.sortKey.1 }
      return $0.sortKey.2 < $1.sortKey.2
    }

    let resultValues = values.map { $0.value }
    return [
      "results": .array(resultValues),
      "result_count": .number(Double(resultValues.count)),
      "truncated": .boolean(resultValues.count == limit),
    ]
  }

  public func get(contactReference: String) throws -> [String: BrokerJSONValue] {
    guard validReference(contactReference) else { throw BrokerError.invalidArguments }
    switch permission.authorizationState() {
    case .granted: break
    case .notRequested: throw BrokerError.permissionNotRequested
    case .denied: throw BrokerError.permissionDenied
    case .restricted: throw BrokerError.permissionRestricted
    case .unavailable: throw BrokerError.capabilityUnavailable
    }
    guard let identifier = references.identifier(for: contactReference) else {
      throw BrokerError.contactReferenceUnknown
    }
    let keys: [CNKeyDescriptor] = [CNContactIdentifierKey as CNKeyDescriptor,
      CNContactGivenNameKey as CNKeyDescriptor, CNContactFamilyNameKey as CNKeyDescriptor,
      CNContactOrganizationNameKey as CNKeyDescriptor,
      CNContactEmailAddressesKey as CNKeyDescriptor, CNContactPhoneNumbersKey as CNKeyDescriptor]
    do {
      let contact = try store.unifiedContact(withIdentifier: identifier, keysToFetch: keys)
      guard contact.identifier == identifier else { throw BrokerError.contactReferenceUnknown }
      let given = contact.givenName, family = contact.familyName, organization = contact.organizationName
      let display = [given, family].filter { !$0.isEmpty }.joined(separator: " ")
      let emails = contact.emailAddresses.prefix(10).map { BrokerJSONValue.object([
        "label": sanitized(normalizeContactLabel($0.label), limit: 50),
        "address": sanitized(String($0.value), limit: 254)]) }
      let phones = contact.phoneNumbers.prefix(10).map { item -> BrokerJSONValue in
        let number = item.value.stringValue
        return .object(["label": sanitized(normalizeContactLabel(item.label), limit: 50),
          "number": sanitized(number, limit: 80),
          "normalized_number": sanitized(number.filter { $0.isNumber || $0 == "+" }, limit: 80)])
      }
      return ["contact_reference": .string(contactReference),
        "display_name": sanitized(display.isEmpty ? organization : display, limit: 200),
        "given_name": sanitized(given, limit: 200), "family_name": sanitized(family, limit: 200),
        "organization": sanitized(organization, limit: 200), "emails": .array(emails),
        "phones": .array(phones)]
    } catch let error as BrokerError { throw error }
    catch { throw BrokerError.contactReferenceUnknown }
  }

  func opaqueReference(for identifier: String) -> String? {
    guard !identifier.isEmpty else { return nil }
    let digest = Insecure.SHA1.hash(data: secret + Data(identifier.utf8))
    return "contact_" + digest.prefix(12).map { String(format: "%02x", $0) }.joined()
  }

  func normalizeContactLabel(_ label: NSString?) -> String {
    guard let label else { return "" }
    let value = String(label)
    switch value {
    case CNLabelPhoneNumberMobile: return "mobile"
    case CNLabelPhoneNumberiPhone: return "iphone"
    case CNLabelPhoneNumberMain: return "main"
    case CNLabelHome: return "home"
    case CNLabelWork: return "work"
    case CNLabelOther: return "other"
    default:
      let scalars = value.unicodeScalars
        .filter { $0.value >= 32 && $0.value != 127 }
        .map(String.init)
        .joined()
      let stripped = scalars
        .replacingOccurrences(of: "*$!<", with: "")
        .replacingOccurrences(of: ">!$*", with: "")
      return String(stripped.prefix(50))
    }
  }

  func normalizeContactLabel(_ label: String?) -> String {
    normalizeContactLabel(label as NSString?)
  }

  private func sanitized(_ value: String, limit: Int) -> BrokerJSONValue {
    let clean = value.unicodeScalars
      .filter { $0.value >= 32 && $0.value != 127 }
      .map(String.init)
      .joined()
    return .string(String(clean.prefix(limit)))
  }

  private func validReference(_ value: String) -> Bool {
    let body = value.dropFirst(8)
    return value.hasPrefix("contact_") && (8...80).contains(value.count)
      && body.allSatisfy { $0.isLetter || $0.isNumber || $0 == "_" || $0 == "-" }
  }
}
