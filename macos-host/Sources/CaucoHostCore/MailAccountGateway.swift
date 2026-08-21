import Foundation

public protocol MailAccountGateway: Sendable {
  func listAccounts() throws -> [String: BrokerJSONValue]
  func listMailboxes(accountReference: String) throws -> [String: BrokerJSONValue]
}

public struct MailMailboxLocator: Hashable, Sendable {
  public let accountIdentifier: Int32
  public let mailboxIdentifier: Int32

  public init(accountIdentifier: Int32, mailboxIdentifier: Int32) {
    self.accountIdentifier = accountIdentifier
    self.mailboxIdentifier = mailboxIdentifier
  }
}

public final class MailAccountReferenceRegistry: @unchecked Sendable {
  private let lock = NSLock()
  private let accountCapacity: Int
  private let mailboxCapacity: Int

  private var accountByIdentifier: [Int32: String] = [:]
  private var accountByReference: [String: Int32] = [:]
  private var accountOrder: [Int32] = []
  private var mailboxByLocator: [MailMailboxLocator: String] = [:]
  private var mailboxByReference: [String: MailMailboxLocator] = [:]
  private var mailboxOrder: [MailMailboxLocator] = []

  public init(accountCapacity: Int = 20, mailboxCapacity: Int = 2_000) {
    self.accountCapacity = max(1, accountCapacity)
    self.mailboxCapacity = max(1, mailboxCapacity)
  }

  public func accountReference(for identifier: Int32) -> String {
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

  public func accountIdentifier(for reference: String) -> Int32? {
    lock.lock()
    defer { lock.unlock() }
    return accountByReference[reference]
  }

  public func mailboxReference(
    accountIdentifier: Int32, mailboxIdentifier: Int32
  ) -> String {
    let locator = MailMailboxLocator(
      accountIdentifier: accountIdentifier, mailboxIdentifier: mailboxIdentifier)
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

  public func mailboxLocator(for reference: String) -> MailMailboxLocator? {
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
    let script = """
    tell application "Mail"
      set sourceAccounts to every account
      set totalCount to count of sourceAccounts
      set selectedCount to 20
      if totalCount < selectedCount then set selectedCount to totalCount
      set outputRows to {}
      repeat with i from 1 to selectedCount
        set accountItem to item i of sourceAccounts
        set end of outputRows to {id of accountItem, name of accountItem, email addresses of accountItem}
      end repeat
      return {totalCount, outputRows}
    end tell
    """
    let (totalCount, rows) = try executeMailList(script)
    var results: [BrokerJSONValue] = []
    results.reserveCapacity(min(20, rows.numberOfItems))
    if rows.numberOfItems > 0 {
      for index in 1...rows.numberOfItems {
        guard let row = rows.atIndex(index), row.numberOfItems == 3,
          let identifierDescriptor = row.atIndex(1),
          let nameDescriptor = row.atIndex(2),
          let addressesDescriptor = row.atIndex(3)
        else { continue }
        let identifier = identifierDescriptor.int32Value
        guard identifier > 0 else { continue }
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
            "account_reference": .string(references.accountReference(for: identifier)),
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
    let script = """
    tell application "Mail"
      set targetAccount to missing value
      repeat with accountItem in every account
        if id of accountItem is \(accountIdentifier) then
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
        set end of outputRows to {id of mailboxItem, name of mailboxItem}
      end repeat
      return {totalCount, outputRows}
    end tell
    """
    let (totalCount, rows) = try executeMailList(script)
    guard totalCount >= 0 else { throw BrokerError.mailAccountReferenceUnknown }
    var results: [BrokerJSONValue] = []
    results.reserveCapacity(min(100, rows.numberOfItems))
    if rows.numberOfItems > 0 {
      for index in 1...rows.numberOfItems {
        guard let row = rows.atIndex(index), row.numberOfItems == 2,
          let identifierDescriptor = row.atIndex(1),
          let nameDescriptor = row.atIndex(2)
        else { continue }
        let mailboxIdentifier = identifierDescriptor.int32Value
        guard mailboxIdentifier > 0 else { continue }
        results.append(
          .object([
            "mailbox_reference": .string(
              references.mailboxReference(
                accountIdentifier: accountIdentifier, mailboxIdentifier: mailboxIdentifier)),
            "name": .string(mailSanitized(nameDescriptor.stringValue ?? "", limit: 300)),
          ]))
      }
    }
    return mailBoundedResult(results: results, totalCount: totalCount)
  }
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
