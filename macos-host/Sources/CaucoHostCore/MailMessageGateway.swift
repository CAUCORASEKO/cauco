import Foundation

public protocol MailMessageGateway: Sendable {
  func listMessages(mailboxReference: String, limit: Int) throws -> [String: BrokerJSONValue]
}

public final class MailMessageReferenceRegistry: @unchecked Sendable {
  private let lock = NSLock()
  private let capacity: Int

  private var byIdentifier: [Int32: String] = [:]
  private var byReference: [String: Int32] = [:]
  private var order: [Int32] = []

  public init(capacity: Int = 500) {
    self.capacity = max(1, capacity)
  }

  public func reference(for identifier: Int32) -> String {
    lock.lock()
    defer { lock.unlock() }

    if let existing = byIdentifier[identifier] {
      return existing
    }

    let reference =
      "mailmsg_"
      + UUID().uuidString
        .replacingOccurrences(of: "-", with: "")
        .lowercased()

    byIdentifier[identifier] = reference
    byReference[reference] = identifier
    order.append(identifier)

    while order.count > capacity {
      let oldest = order.removeFirst()
      if let oldReference = byIdentifier.removeValue(forKey: oldest) {
        byReference.removeValue(forKey: oldReference)
      }
    }

    return reference
  }

  public func identifier(for reference: String) -> Int32? {
    lock.lock()
    defer { lock.unlock() }
    return byReference[reference]
  }
}

public final class NativeMailMessageGateway: MailMessageGateway, @unchecked Sendable {
  private let accountReferences: MailAccountReferenceRegistry
  private let references: MailMessageReferenceRegistry

  public init(
    accountReferences: MailAccountReferenceRegistry = MailAccountReferenceRegistry(),
    references: MailMessageReferenceRegistry = MailMessageReferenceRegistry()
  ) {
    self.accountReferences = accountReferences
    self.references = references
  }

  public func listMessages(
    mailboxReference: String, limit: Int
  ) throws -> [String: BrokerJSONValue] {
    guard (1...20).contains(limit) else {
      throw BrokerError.invalidArguments
    }
    guard let locator = accountReferences.mailboxLocator(for: mailboxReference) else {
      throw BrokerError.mailMailboxReferenceUnknown
    }

    let script = mailMessagesScript(locator: locator, limit: limit)

    var errorInfo: NSDictionary?

    guard let appleScript = NSAppleScript(source: script) else {
      throw BrokerError.internalFailure
    }

    let descriptor = appleScript.executeAndReturnError(&errorInfo)

    if errorInfo != nil {
      throw BrokerError.internalFailure
    }

    guard descriptor.numberOfItems == 2,
      let totalDescriptor = descriptor.atIndex(1),
      let rowsDescriptor = descriptor.atIndex(2)
    else {
      throw BrokerError.internalFailure
    }

    let rawTotalCount = Int(totalDescriptor.int32Value)
    guard rawTotalCount >= 0 else {
      throw BrokerError.mailMailboxReferenceUnknown
    }
    let totalCount = rawTotalCount

    var results: [BrokerJSONValue] = []
    results.reserveCapacity(min(limit, rowsDescriptor.numberOfItems))

    let rowCount = min(limit, rowsDescriptor.numberOfItems)
    if rowCount > 0 {
      for index in 1...rowCount {
        guard let row = rowsDescriptor.atIndex(index),
          row.numberOfItems == 5,
          let idDescriptor = row.atIndex(1),
          let senderDescriptor = row.atIndex(2),
          let subjectDescriptor = row.atIndex(3),
          let dateDescriptor = row.atIndex(4),
          let readDescriptor = row.atIndex(5)
        else {
          continue
        }

        let identifier = idDescriptor.int32Value
        guard identifier > 0 else {
          continue
        }

        let reference = references.reference(for: identifier)
        let sender = mailSanitized(senderDescriptor.stringValue ?? "", limit: 320)
        let subject = mailSanitized(subjectDescriptor.stringValue ?? "", limit: 300)

        guard let dateReceived = mailISO8601Date(from: dateDescriptor) else {
          continue
        }

        results.append(
          .object([
            "message_reference": .string(reference),
            "sender": .string(sender),
            "subject": .string(subject),
            "date_received": .string(dateReceived),
            "read": .boolean(readDescriptor.booleanValue),
          ]))
      }
    }

    return [
      "results": .array(results),
      "result_count": .number(Double(results.count)),
      "truncated": .boolean(totalCount > results.count),
    ]
  }
}

func mailMessagesScript(locator: MailMailboxLocator, limit: Int) -> String {
  """
    tell application "Mail"
      set targetAccount to missing value
      repeat with accountItem in every account
        if id of accountItem is \(locator.accountIdentifier) then
          set targetAccount to accountItem
          exit repeat
        end if
      end repeat
      if targetAccount is missing value then return {-1, {}}

      set targetMailbox to missing value
      repeat with mailboxItem in every mailbox of targetAccount
        if id of mailboxItem is \(locator.mailboxIdentifier) then
          set targetMailbox to mailboxItem
          exit repeat
        end if
      end repeat
      if targetMailbox is missing value then return {-1, {}}

      set sourceMessages to messages of targetMailbox
      set totalCount to count of sourceMessages
      set selectedCount to \(limit)

      if totalCount < selectedCount then
        set selectedCount to totalCount
      end if

      set outputRows to {}

      repeat with i from 1 to selectedCount
        set msg to item i of sourceMessages

        set end of outputRows to {¬
          id of msg, ¬
          sender of msg, ¬
          subject of msg, ¬
          date received of msg, ¬
          read status of msg}
      end repeat

      return {totalCount, outputRows}
    end tell
    """
}

func mailISO8601Date(from descriptor: NSAppleEventDescriptor) -> String? {
  // AppleEvent typeLongDateTime.
  guard descriptor.descriptorType == 1_818_522_656 else {
    return nil
  }

  let data = descriptor.data
  guard data.count == 8 else {
    return nil
  }

  var raw: Int64 = 0

  _ = withUnsafeMutableBytes(of: &raw) { destination in
    data.copyBytes(to: destination)
  }

  let secondsFrom1904 = Int64(littleEndian: raw)

  // AppleEvent LongDateTime epoch: 1904-01-01 00:00:00 UTC.
  let appleEpoch = Date(timeIntervalSince1970: -2_082_844_800)
  let date = appleEpoch.addingTimeInterval(
    TimeInterval(secondsFrom1904)
  )

  let formatter = ISO8601DateFormatter()
  formatter.formatOptions = [
    .withInternetDateTime,
    .withFractionalSeconds,
  ]

  return formatter.string(from: date)
}

func mailSanitized(_ value: String, limit: Int) -> String {
  guard limit > 0 else {
    return ""
  }

  return String(
    value.unicodeScalars
      .filter { scalar in
        let code = scalar.value
        return !(code <= 0x1F || (0x7F...0x9F).contains(code))
      }
      .prefix(limit)
  )
}
