import Foundation

public protocol MailAccountGateway: Sendable {
  func listAccounts() throws -> [String: BrokerJSONValue]
  func listMailboxes(accountReference: String) throws -> [String: BrokerJSONValue]
}

struct MailMailboxLocator: Hashable, Sendable {
  let accountIdentifier: String
  let mailboxIndex: Int
  let expectedName: String
}

public final class MailAccountReferenceRegistry: @unchecked Sendable {
  private let lock = NSLock()
  private let accountCapacity: Int
  private let mailboxCapacity: Int

  private var accountByIdentifier: [String: String] = [:]
  private var accountByReference: [String: String] = [:]
  private var accountOrder: [String] = []
  private var mailboxByLocator: [MailMailboxLocator: String] = [:]
  private var mailboxByReference: [String: MailMailboxLocator] = [:]
  private var mailboxOrder: [MailMailboxLocator] = []

  public init(accountCapacity: Int = 20, mailboxCapacity: Int = 2_000) {
    self.accountCapacity = max(1, accountCapacity)
    self.mailboxCapacity = max(1, mailboxCapacity)
  }

  func accountReference(for identifier: String) -> String? {
    guard mailNativeAccountIdentifierIsValid(identifier) else { return nil }
    lock.lock()
    defer { lock.unlock() }
    if let existing = accountByIdentifier[identifier] { return existing }
    let reference = opaqueMailReference(prefix: "mailacct")
    accountByIdentifier[identifier] = reference
    accountByReference[reference] = identifier
    accountOrder.append(identifier)
    while accountOrder.count > accountCapacity {
      let oldest = accountOrder.removeFirst()
      if let removed = accountByIdentifier.removeValue(forKey: oldest) {
        accountByReference.removeValue(forKey: removed)
      }
    }
    return reference
  }

  func accountIdentifier(for reference: String) -> String? {
    lock.lock()
    defer { lock.unlock() }
    return accountByReference[reference]
  }

  func mailboxReference(
    accountIdentifier: String, mailboxIndex: Int, expectedName: String
  ) -> String? {
    guard mailNativeAccountIdentifierIsValid(accountIdentifier), (1...100).contains(mailboxIndex),
      !expectedName.isEmpty, expectedName.count <= 300,
      mailSanitized(expectedName, limit: 300) == expectedName
    else { return nil }
    let locator = MailMailboxLocator(
      accountIdentifier: accountIdentifier, mailboxIndex: mailboxIndex, expectedName: expectedName)
    lock.lock()
    defer { lock.unlock() }
    if let existing = mailboxByLocator[locator] { return existing }
    let reference = opaqueMailReference(prefix: "mailbox")
    mailboxByLocator[locator] = reference
    mailboxByReference[reference] = locator
    mailboxOrder.append(locator)
    while mailboxOrder.count > mailboxCapacity {
      let oldest = mailboxOrder.removeFirst()
      if let removed = mailboxByLocator.removeValue(forKey: oldest) {
        mailboxByReference.removeValue(forKey: removed)
      }
    }
    return reference
  }

  func mailboxLocator(for reference: String) -> MailMailboxLocator? {
    lock.lock()
    defer { lock.unlock() }
    return mailboxByReference[reference]
  }
}

public final class NativeMailAccountGateway: MailAccountGateway, @unchecked Sendable {
  private let references: MailAccountReferenceRegistry

  public init(
    references: MailAccountReferenceRegistry = MailAccountReferenceRegistry()
  ) {
    self.references = references
  }

  public func listAccounts() throws -> [String: BrokerJSONValue] {
    let (totalCount, rows) = try executeMailList(mailAccountsScript())
    var results: [BrokerJSONValue] = []
    results.reserveCapacity(min(20, rows.numberOfItems))
    if rows.numberOfItems > 0 {
      for index in 1...rows.numberOfItems {
        guard let row = rows.atIndex(index), row.numberOfItems == 3,
          let identifierDescriptor = row.atIndex(1),
          let nameDescriptor = row.atIndex(2),
          let addressesDescriptor = row.atIndex(3)
        else { continue }
        guard let identifier = identifierDescriptor.stringValue,
          let accountReference = references.accountReference(for: identifier)
        else { continue }
        var addresses: [BrokerJSONValue] = []
        if addressesDescriptor.numberOfItems > 0 {
          for addressIndex in 1...min(20, addressesDescriptor.numberOfItems) {
            guard let address = addressesDescriptor.atIndex(addressIndex)?.stringValue else {
              continue
            }
            addresses.append(.string(mailSanitized(address, limit: 320)))
          }
        }
        results.append(
          .object([
            "account_reference": .string(accountReference),
            "name": .string(mailSanitized(nameDescriptor.stringValue ?? "", limit: 300)),
            "email_addresses": .array(addresses),
          ]))
      }
    }
    return mailBoundedResult(results: results, totalCount: totalCount)
  }

  public func listMailboxes(accountReference: String) throws -> [String: BrokerJSONValue] {
    guard let accountIdentifier = references.accountIdentifier(for: accountReference) else {
      throw BrokerError.mailAccountReferenceUnknown
    }
    let script = mailMailboxesScript(accountIdentifier: accountIdentifier)
    let (totalCount, rows) = try executeMailList(script)
    guard totalCount >= 0 else { throw BrokerError.mailAccountReferenceUnknown }
    var results: [BrokerJSONValue] = []
    results.reserveCapacity(min(100, rows.numberOfItems))
    if rows.numberOfItems > 0 {
      for index in 1...rows.numberOfItems {
        guard let row = rows.atIndex(index), row.numberOfItems == 2,
          let indexDescriptor = row.atIndex(1),
          let nameDescriptor = row.atIndex(2),
          let rawName = nameDescriptor.stringValue
        else { continue }
        let mailboxIndex = Int(indexDescriptor.int32Value)
        let name = mailSanitized(rawName, limit: 300)
        guard rawName == name, !name.isEmpty,
          let mailboxReference = references.mailboxReference(
            accountIdentifier: accountIdentifier, mailboxIndex: mailboxIndex, expectedName: name)
        else { continue }
        results.append(
          .object([
            "mailbox_reference": .string(mailboxReference),
            "name": .string(name),
          ]))
      }
    }
    return mailBoundedResult(results: results, totalCount: totalCount)
  }
}

func mailAccountsScript() -> String {
  """
  tell application "Mail"
    set sourceAccounts to every account
    set totalCount to count of sourceAccounts
    set selectedCount to 20
    if totalCount < selectedCount then set selectedCount to totalCount
    set outputRows to {}
    repeat with i from 1 to selectedCount
      set accountItem to item i of sourceAccounts
      set end of outputRows to {id of accountItem as text, name of accountItem, email addresses of accountItem}
    end repeat
    return {totalCount, outputRows}
  end tell
  """
}

func mailMailboxesScript(accountIdentifier: String) -> String {
  let accountLiteral = mailAppleScriptStringLiteral(accountIdentifier)
  return """
    tell application "Mail"
      set targetAccount to missing value
      repeat with accountItem in every account
        if (id of accountItem as text) is \(accountLiteral) then
          set targetAccount to accountItem
          exit repeat
        end if
      end repeat
      if targetAccount is missing value then return {-1, {}}
      set sourceMailboxes to every mailbox of targetAccount
      set totalCount to count of sourceMailboxes
      set selectedCount to 100
      if totalCount < selectedCount then set selectedCount to totalCount
      set outputRows to {}
      repeat with i from 1 to selectedCount
        set mailboxItem to item i of sourceMailboxes
        set end of outputRows to {i, name of mailboxItem}
      end repeat
      return {totalCount, outputRows}
    end tell
    """
}

func mailNativeAccountIdentifierIsValid(_ identifier: String) -> Bool {
  !identifier.isEmpty && identifier.count <= 200
    && identifier.unicodeScalars.allSatisfy { scalar in
      let code = scalar.value
      return !(code <= 0x1F || (0x7F...0x9F).contains(code))
    }
}

func mailAppleScriptStringLiteral(_ value: String) -> String {
  let escaped =
    value
    .replacingOccurrences(of: "\\", with: "\\\\")
    .replacingOccurrences(of: "\"", with: "\\\"")
  return "\"\(escaped)\""
}

private func opaqueMailReference(prefix: String) -> String {
  prefix + "_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
}

private func executeMailList(_ script: String) throws -> (Int, NSAppleEventDescriptor) {
  var errorInfo: NSDictionary?
  guard let appleScript = NSAppleScript(source: script) else { throw BrokerError.internalFailure }
  let descriptor = appleScript.executeAndReturnError(&errorInfo)
  guard errorInfo == nil, descriptor.numberOfItems == 2,
    let totalDescriptor = descriptor.atIndex(1), let rowsDescriptor = descriptor.atIndex(2)
  else { throw BrokerError.internalFailure }
  return (Int(totalDescriptor.int32Value), rowsDescriptor)
}

private func mailBoundedResult(
  results: [BrokerJSONValue], totalCount: Int
) -> [String: BrokerJSONValue] {
  [
    "results": .array(results),
    "result_count": .number(Double(results.count)),
    "truncated": .boolean(totalCount > results.count),
  ]
}
