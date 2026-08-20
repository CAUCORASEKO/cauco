import Foundation

public protocol MailDraftGateway: Sendable {
  func createDraft(recipient: String, subject: String, body: String) throws
    -> [String: BrokerJSONValue]
}

public final class NativeMailDraftGateway: MailDraftGateway, @unchecked Sendable {
  public init() {}

  public func createDraft(
    recipient: String,
    subject: String,
    body: String
  ) throws -> [String: BrokerJSONValue] {
    guard Self.validRecipient(recipient),
      !subject.isEmpty,
      subject.count <= 300,
      body.count <= 4_000
    else {
      throw BrokerError.invalidArguments
    }

    let script = """
    tell application "Mail"
      set newMessage to make new outgoing message with properties {subject:\(Self.literal(subject)), content:\(Self.literal(body)), visible:false}
      tell newMessage
        make new to recipient at end of to recipients with properties {address:\(Self.literal(recipient))}
      end tell
      save newMessage
    end tell
    """

    var errorInfo: NSDictionary?
    guard let appleScript = NSAppleScript(source: script) else {
      throw BrokerError.internalFailure
    }

    let result = appleScript.executeAndReturnError(&errorInfo)
    if errorInfo != nil {
      throw BrokerError.internalFailure
    }

    _ = result

    return [
      "recipient": .string(recipient),
      "subject": .string(subject),
      "draft_created": .boolean(true),
    ]
  }

  private static func validRecipient(_ value: String) -> Bool {
    guard !value.isEmpty, value.count <= 254 else { return false }
    guard !value.contains(where: { $0.isWhitespace || $0.isNewline }) else { return false }

    let parts = value.split(separator: "@", omittingEmptySubsequences: false)
    return parts.count == 2 && !parts[0].isEmpty && !parts[1].isEmpty
  }

  private static func literal(_ value: String) -> String {
    let escaped =
      value
      .replacingOccurrences(of: "\\", with: "\\\\")
      .replacingOccurrences(of: "\"", with: "\\\"")
      .replacingOccurrences(of: "\r\n", with: "\\n")
      .replacingOccurrences(of: "\r", with: "\\n")
      .replacingOccurrences(of: "\n", with: "\\n")

    return "\"\(escaped)\""
  }
}
