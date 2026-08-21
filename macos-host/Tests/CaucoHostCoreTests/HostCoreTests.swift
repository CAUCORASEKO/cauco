import Contacts
import Darwin
import EventKit
import XCTest

@testable import CaucoHostCore

final class HostCoreTests: XCTestCase {
  private var temporary: [URL] = []
  override func tearDown() {
    temporary.forEach { try? FileManager.default.removeItem(at: $0) }
    temporary.removeAll()
  }
  private func repository(valid: Bool = true, executable: Bool = true) throws -> URL {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    temporary.append(root)
    let fm = FileManager.default
    try fm.createDirectory(
      at: root.appendingPathComponent("core"), withIntermediateDirectories: true)
    try fm.createDirectory(
      at: root.appendingPathComponent(".venv/bin"), withIntermediateDirectories: true)
    if valid {
      fm.createFile(
        atPath: root.appendingPathComponent("core/pyproject.toml").path, contents: Data())
    }
    if executable {
      fm.createFile(atPath: root.appendingPathComponent(".venv/bin/python").path, contents: Data())
      try fm.setAttributes(
        [.posixPermissions: 0o700],
        ofItemAtPath: root.appendingPathComponent(".venv/bin/python").path)
    }
    return root
  }
  func testAuthorizationMapping() {
    XCTAssertEqual(NativeContactsPermissionGateway.map(.notDetermined), .notRequested)
    XCTAssertEqual(NativeContactsPermissionGateway.map(.denied), .denied)
    XCTAssertEqual(NativeContactsPermissionGateway.map(.restricted), .restricted)
  }
  func testCalendarAuthorizationMappingIsReadSafe() {
    if #available(macOS 14.0, *) {
      XCTAssertEqual(NativeCalendarPermissionGateway.map(.fullAccess), .granted)
      XCTAssertEqual(NativeCalendarPermissionGateway.map(.writeOnly), .unavailable)
      XCTAssertNotEqual(NativeCalendarPermissionGateway.map(.writeOnly), .granted)
      XCTAssertEqual(NativeCalendarPermissionGateway.map(.notDetermined), .notRequested)
    }
    XCTAssertEqual(NativeCalendarPermissionGateway.mapLegacy(.authorized), .granted)
  }
  func testCalendarPermissionRequestIsExplicitAndDoesNotReadData() {
    let fake = FakeCalendarPermission(.notRequested)
    XCTAssertEqual(fake.authorizationState(), .notRequested)
    XCTAssertEqual(fake.requests, 0)
    XCTAssertEqual(fake.dataReads, 0)
    fake.requestAccess { state in XCTAssertEqual(state, .granted) }
    XCTAssertEqual(fake.requests, 1)
    XCTAssertEqual(fake.dataReads, 0)
  }
  func testNoConfiguredRepository() {
    let d = UserDefaults(suiteName: UUID().uuidString)!
    XCTAssertThrowsError(
      try RepositoryConfiguration.resolve(
        userDefaults: d, environment: [:],
        workingDirectory: URL(fileURLWithPath: "/Applications/Cauco.app"))
    ) { XCTAssertEqual($0 as? RepositoryResolutionError, .unconfigured) }
  }
  func testFilesystemRootRejected() {
    XCTAssertThrowsError(try RepositoryConfiguration.validate(URL(fileURLWithPath: "/"))) {
      XCTAssertEqual($0 as? RepositoryResolutionError, .rootRejected)
    }
  }
  func testValidRepositoryAndExecutablePath() throws {
    let root = try repository()
    let result = try RepositoryConfiguration.validate(root)
    XCTAssertEqual(result.repository, root.standardizedFileURL)
    XCTAssertEqual(
      result.executable, root.standardizedFileURL.appendingPathComponent(".venv/bin/python"))
  }
  func testRegularExecutableAccepted() throws {
    XCTAssertNoThrow(try RepositoryConfiguration.validate(try repository()))
  }
  func testValidSymlinkToExecutableAcceptedButLogicalEntrypointLaunched() throws {
    let root = try repository(executable: false)
    let outside = root.deletingLastPathComponent().appendingPathComponent(UUID().uuidString)
    temporary.append(outside)
    FileManager.default.createFile(atPath: outside.path, contents: Data())
    try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: outside.path)
    let logical = root.appendingPathComponent(".venv/bin/python")
    try FileManager.default.createSymbolicLink(at: logical, withDestinationURL: outside)
    let result = try RepositoryConfiguration.validate(root)
    XCTAssertEqual(result.executable, logical.standardizedFileURL)
  }
  func testBrokenSymlinkRejected() throws {
    let root = try repository(executable: false)
    let logical = root.appendingPathComponent(".venv/bin/python")
    try FileManager.default.createSymbolicLink(
      at: logical, withDestinationURL: root.appendingPathComponent("missing-python"))
    XCTAssertThrowsError(try RepositoryConfiguration.validate(root)) {
      XCTAssertEqual($0 as? RepositoryResolutionError, .missingPython(logical))
    }
  }
  func testSymlinkToDirectoryRejected() throws {
    let root = try repository(executable: false)
    let destination = root.appendingPathComponent("python-directory")
    try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: false)
    let logical = root.appendingPathComponent(".venv/bin/python")
    try FileManager.default.createSymbolicLink(at: logical, withDestinationURL: destination)
    XCTAssertThrowsError(try RepositoryConfiguration.validate(root)) {
      XCTAssertEqual($0 as? RepositoryResolutionError, .pythonNotRegular(logical))
    }
  }
  func testSymlinkToNonExecutableFileRejected() throws {
    let root = try repository(executable: false)
    let destination = root.appendingPathComponent("python-file")
    FileManager.default.createFile(atPath: destination.path, contents: Data())
    try FileManager.default.setAttributes(
      [.posixPermissions: 0o600], ofItemAtPath: destination.path)
    let logical = root.appendingPathComponent(".venv/bin/python")
    try FileManager.default.createSymbolicLink(at: logical, withDestinationURL: destination)
    XCTAssertThrowsError(try RepositoryConfiguration.validate(root)) {
      XCTAssertEqual($0 as? RepositoryResolutionError, .pythonNotExecutable(logical))
    }
  }
  func testMissingManifestRejected() throws {
    let root = try repository(valid: false)
    XCTAssertThrowsError(try RepositoryConfiguration.validate(root)) {
      XCTAssertEqual(
        $0 as? RepositoryResolutionError,
        .missingCoreManifest(root.appendingPathComponent("core/pyproject.toml")))
    }
  }
  func testMissingPythonRejected() throws {
    let root = try repository(executable: false)
    XCTAssertThrowsError(try RepositoryConfiguration.validate(root)) {
      XCTAssertEqual(
        $0 as? RepositoryResolutionError,
        .missingPython(root.appendingPathComponent(".venv/bin/python")))
    }
  }
  func testNonExecutablePythonRejected() throws {
    let root = try repository()
    let python = root.appendingPathComponent(".venv/bin/python")
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: python.path)
    XCTAssertThrowsError(try RepositoryConfiguration.validate(root)) {
      XCTAssertEqual($0 as? RepositoryResolutionError, .pythonNotExecutable(python))
    }
  }
  func testUserDefaultsPrecedesEnvironmentAndSourceIsDisplayedData() throws {
    let selected = try repository()
    let env = try repository()
    let d = UserDefaults(suiteName: UUID().uuidString)!
    d.set(selected.path, forKey: repositoryPathDefaultsKey)
    let result = try RepositoryConfiguration.resolve(
      userDefaults: d, environment: [repositoryPathEnvironmentKey: env.path],
      workingDirectory: URL(fileURLWithPath: "/Applications/Cauco.app"))
    XCTAssertEqual(result.repository, selected.standardizedFileURL)
    XCTAssertEqual(result.source, .configured)
    XCTAssertFalse("Not configured" == "\(result.source.rawValue): \(result.repository.path)")
  }
  func testEnvironmentFallbackAndSource() throws {
    let root = try repository()
    let d = UserDefaults(suiteName: UUID().uuidString)!
    let result = try RepositoryConfiguration.resolve(
      userDefaults: d, environment: [repositoryPathEnvironmentKey: root.path],
      workingDirectory: URL(fileURLWithPath: "/Applications/Cauco.app"))
    XCTAssertEqual(result.repository, root.standardizedFileURL)
    XCTAssertEqual(result.source, .environment)
  }
  func testInstalledAppDoesNotProduceFilesystemRoot() {
    XCTAssertThrowsError(
      try RepositoryConfiguration.resolve(
        userDefaults: UserDefaults(suiteName: UUID().uuidString)!, environment: [:],
        workingDirectory: URL(fileURLWithPath: "/Applications/Cauco.app"))
    ) { XCTAssertFalse(($0 as? RepositoryResolutionError) == .rootRejected) }
  }
  func testRepositoryBuildTreeFallbackIsNotUnconfigured() throws {
    let root = try repository()
    let result = try RepositoryConfiguration.resolve(
      userDefaults: UserDefaults(suiteName: UUID().uuidString)!, environment: [:],
      workingDirectory: root)
    XCTAssertEqual(result.repository, root.standardizedFileURL)
    XCTAssertEqual(result.source, .developmentFallback)
  }
  func testFixedArgumentsRemainUnchanged() {
    let c = CoreLaunchConfiguration(
      executable: URL(fileURLWithPath: "/tmp/python"), repository: URL(fileURLWithPath: "/tmp/repo")
    )
    XCTAssertEqual(
      c.arguments,
      ["-m", "uvicorn", "cauco_core.main:app", "--host", "127.0.0.1", "--port", "8765"])
    XCTAssertTrue(isLocalCoreURL(c.url))
    XCTAssertFalse(c.arguments.contains(where: { $0.contains(";") }))
  }
  func testSelectionDoesNotStartCoreAndClearingIsUnconfigured() throws {
    let root = try repository()
    let d = UserDefaults(suiteName: UUID().uuidString)!
    d.set(root.path, forKey: repositoryPathDefaultsKey)
    XCTAssertNotNil(d.string(forKey: repositoryPathDefaultsKey))
    d.removeObject(forKey: repositoryPathDefaultsKey)
    XCTAssertNil(d.string(forKey: repositoryPathDefaultsKey))
    XCTAssertThrowsError(
      try RepositoryConfiguration.resolve(
        userDefaults: d, environment: [:],
        workingDirectory: URL(fileURLWithPath: "/Applications/Cauco.app")))
  }
  func testArbitraryExecutablePathCannotBeSupplied() throws {
    let root = try repository()
    let arbitrary = root.appendingPathComponent("arbitrary-python")
    FileManager.default.createFile(atPath: arbitrary.path, contents: Data())
    try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: arbitrary.path)
    let result = try RepositoryConfiguration.validate(root)
    XCTAssertNotEqual(result.executable, arbitrary)
  }
  func testBoundedDiagnosticsAndLocalHealth() {
    XCTAssertEqual(boundedDiagnostic(String(repeating: "x", count: 10), limit: 4).count, 4)
    XCTAssertFalse(isLocalCoreURL(URL(string: "http://localhost:8765")!))
    XCTAssertEqual(
      URL(string: "http://127.0.0.1:8765")!.appendingPathComponent("health").absoluteString,
      "http://127.0.0.1:8765/health")
  }
  func testBrokerStatusAndPermissionMapping() throws {
    let broker = NativeCapabilityBroker(permission: FakePermission(.granted))
    let response = broker.handle(try request(.contactsStatus))
    XCTAssertEqual(response.outcome, .success)
    XCTAssertEqual(response.method, "contacts.status.v1")
    XCTAssertEqual(response.result?["state"], .string("granted"))
    XCTAssertEqual(response.result?["available"], .boolean(true))
  }
  func testBrokerStatusIsObservationalAndNoRequestOccurs() throws {
    let fake = FakePermission(.denied)
    let response = NativeCapabilityBroker(permission: fake).handle(try request(.contactsStatus))
    XCTAssertEqual(response.result?["state"], .string("denied"))
    XCTAssertEqual(fake.requests, 0)
  }
  func testBrokerRejectsUnsupportedProtocolAndInvalidRequest() throws {
    XCTAssertThrowsError(
      try NativeCapabilityRequest(
        protocolVersion: "v0", requestId: "req-1", capability: .contactsStatus, requesterId: "core",
        explicitUserRequest: false, requestLocale: "en", responseLocale: "en", arguments: [:]))
    XCTAssertThrowsError(
      try NativeCapabilityRequest(
        requestId: "BAD ID", capability: .contactsStatus, requesterId: "core",
        explicitUserRequest: false, requestLocale: "en", responseLocale: "en", arguments: [:]))
  }
  func testRegionalLocaleAndUnknownCapabilityDecode() throws {
    XCTAssertNoThrow(
      try NativeCapabilityRequest(
        requestId: "req-1", capability: .contactsStatus, requesterId: "core",
        explicitUserRequest: false, requestLocale: "es-CL", responseLocale: "fi-FI", arguments: [:])
    )
    let data =
      #"{"protocolVersion":"native-capability-broker-v1","requestId":"req-1","capability":"contacts.unknown","requesterId":"core","origin":"localCore","explicitUserRequest":false,"requestLocale":"en","responseLocale":"en","createdAt":"2026-01-01T00:00:00Z","arguments":{}}"#
      .data(using: .utf8)!
    XCTAssertThrowsError(try JSONDecoder().decode(NativeCapabilityRequest.self, from: data))
  }
  func testBrokerRecognizesNotImplementedAndValidatesArguments() throws {
    let broker = NativeCapabilityBroker(
      permission: FakePermission(.granted), contacts: InertContactsDataGateway())
    let search = broker.handle(
      try request(.contactsSearch, args: ["query": .string("Ada"), "limit": .number(2)]))
    XCTAssertEqual(search.outcome, .success)
    XCTAssertEqual(search.result?["result_count"], .number(0))
    XCTAssertEqual(
      broker.handle(
        try request(
          .contactsSearch, args: ["query": .string(""), "limit": .number(2), "extra": .string("x")])
      ).error?.code, "invalid_arguments")
    XCTAssertEqual(
      broker.handle(try request(.contactsListLimited, args: ["limit": .number(21)])).error?.code,
      "invalid_arguments")
    XCTAssertEqual(
      broker.handle(try request(.contactsGet, args: ["contactRef": .string("")])).error?.code,
      "invalid_arguments")
  }
  func testBrokerListLimitedIsImplementedAndBounded() throws {
    let broker = NativeCapabilityBroker(
      permission: FakePermission(.granted), contacts: InertContactsDataGateway())
    let response = broker.handle(
      try request(.contactsListLimited, args: ["limit": .number(1)]))
    XCTAssertEqual(response.outcome, .success)
    XCTAssertEqual(response.method, "contacts.list_limited.v1")
    XCTAssertEqual(
      broker.handle(try request(.contactsListLimited, args: ["limit": .number(21)])).error?.code,
      "invalid_arguments")
  }
  func testMailMessagesBrokerIsBoundedAndDoesNotExposeNativeIDs() throws {
    let mail = FakeMailMessageGateway()

    let broker = NativeCapabilityBroker(
      permission: FakePermission(.granted),
      mailMessages: mail
    )

    let response = broker.handle(
      try request(
        .mailMessagesList,
        args: ["limit": .number(5)]
      )
    )

    XCTAssertEqual(response.outcome, .success)
    XCTAssertEqual(response.method, "mail.messages.list.v1")
    XCTAssertEqual(mail.calls, 1)
    XCTAssertEqual(mail.lastLimit, 5)

    guard case let .array(results)? = response.result?["results"] else {
      return XCTFail("Mail results were missing.")
    }

    XCTAssertEqual(results.count, 1)

    guard case let .object(message) = results[0] else {
      return XCTFail("Mail result was not an object.")
    }

    XCTAssertEqual(
      message["message_reference"],
      .string("mailmsg_0123456789abcdef")
    )
    XCTAssertEqual(message["sender"], .string("Sender <sender@example.com>"))
    XCTAssertEqual(message["subject"], .string("Subject"))
    XCTAssertEqual(
      message["date_received"],
      .string("2026-08-21T05:00:00.000Z")
    )
    XCTAssertEqual(message["read"], .boolean(false))

    XCTAssertNil(message["id"])
    XCTAssertNil(message["message_id"])
    XCTAssertNil(message["native_identifier"])

    let invalid = broker.handle(
      try request(
        .mailMessagesList,
        args: ["limit": .number(21)]
      )
    )

    XCTAssertEqual(invalid.error?.code, "invalid_arguments")
    XCTAssertEqual(mail.calls, 1)
  }

  func testMailAccountAndMailboxReferencesAreOpaqueStableAndBounded() throws {
    let references = MailAccountReferenceRegistry(accountCapacity: 1, mailboxCapacity: 1)
    let firstAccount = references.accountReference(for: 41)
    XCTAssertEqual(firstAccount, references.accountReference(for: 41))
    XCTAssertTrue(firstAccount.hasPrefix("mailacct_"))
    XCTAssertFalse(firstAccount.contains("41"))
    XCTAssertEqual(references.accountIdentifier(for: firstAccount), 41)

    let firstMailbox = references.mailboxReference(
      accountIdentifier: 41, mailboxIdentifier: 501)
    XCTAssertEqual(
      firstMailbox,
      references.mailboxReference(accountIdentifier: 41, mailboxIdentifier: 501))
    XCTAssertTrue(firstMailbox.hasPrefix("mailbox_"))
    XCTAssertFalse(firstMailbox.contains("501"))
    XCTAssertEqual(
      references.mailboxLocator(for: firstMailbox),
      MailMailboxLocator(accountIdentifier: 41, mailboxIdentifier: 501))

    _ = references.accountReference(for: 42)
    _ = references.mailboxReference(accountIdentifier: 42, mailboxIdentifier: 502)
    XCTAssertNil(references.accountIdentifier(for: firstAccount))
    XCTAssertNil(references.mailboxLocator(for: firstMailbox))
    XCTAssertNil(references.accountIdentifier(for: "mailacct_unknown"))
    XCTAssertNil(references.mailboxLocator(for: "mailbox_unknown"))
  }

  func testMailAccountsAndMailboxesBrokerRoutingIsBoundedAndFailClosed() throws {
    let mail = FakeMailAccountGateway()
    let broker = NativeCapabilityBroker(
      permission: FakePermission(.granted),
      mailAccounts: mail
    )

    let accounts = broker.handle(try request(.mailAccountsList, args: [:]))
    XCTAssertEqual(accounts.outcome, .success)
    XCTAssertEqual(accounts.method, "mail.accounts.list.v1")
    XCTAssertEqual(mail.accountCalls, 1)
    guard case let .array(accountRows)? = accounts.result?["results"],
      case let .object(account) = accountRows.first
    else { return XCTFail("Mail account metadata was missing.") }
    XCTAssertEqual(account["account_reference"], .string(mail.accountReference))
    XCTAssertEqual(account["name"], .string("Personal"))
    XCTAssertEqual(account["email_addresses"], .array([.string("user@example.com")]))
    XCTAssertNil(account["id"])
    XCTAssertNil(account["native_identifier"])
    XCTAssertEqual(accounts.result?["result_count"], .number(1))

    let mailboxes = broker.handle(
      try request(
        .mailMailboxesList,
        args: ["account_reference": .string(mail.accountReference)]))
    XCTAssertEqual(mailboxes.outcome, .success)
    XCTAssertEqual(mailboxes.method, "mail.mailboxes.list.v1")
    XCTAssertEqual(mail.mailboxCalls, 1)
    guard case let .array(mailboxRows)? = mailboxes.result?["results"],
      case let .object(mailbox) = mailboxRows.first
    else { return XCTFail("Mail mailbox metadata was missing.") }
    XCTAssertEqual(mailbox["mailbox_reference"], .string("mailbox_0123456789abcdef"))
    XCTAssertEqual(mailbox["name"], .string("Inbox"))
    XCTAssertNil(mailbox["id"])
    XCTAssertNil(mailbox["native_identifier"])
    XCTAssertEqual(mailboxes.result?["result_count"], .number(1))

    let invalidAccounts = broker.handle(
      try request(.mailAccountsList, args: ["limit": .number(20)]))
    XCTAssertEqual(invalidAccounts.error?.code, "invalid_arguments")
    XCTAssertEqual(mail.accountCalls, 1)

    let invalidReference = broker.handle(
      try request(.mailMailboxesList, args: ["account_reference": .string("native-id")]))
    XCTAssertEqual(invalidReference.error?.code, "invalid_arguments")
    XCTAssertEqual(mail.mailboxCalls, 1)

    let unknownReference = broker.handle(
      try request(
        .mailMailboxesList,
        args: ["account_reference": .string("mailacct_ffffffffffffffff")]))
    XCTAssertEqual(unknownReference.outcome, .rejected)
    XCTAssertEqual(unknownReference.error?.code, "mail_account_reference_unknown")
    XCTAssertEqual(mail.mailboxCalls, 2)
  }

  func testMailDraftBrokerIsBoundedAndRoutesOnlyValidatedDrafts() throws {
    let mail = FakeMailDraftGateway()
    let broker = NativeCapabilityBroker(
      permission: FakePermission(.granted),
      mailDrafts: mail
    )

    let response = broker.handle(
      try request(
        .mailDraftCreate,
        args: [
          "recipient": .string("claudio@aisosu.fi"),
          "subject": .string("Prueba Cauco"),
          "body": .string("Draft only"),
        ]
      )
    )

    XCTAssertEqual(response.outcome, .success)
    XCTAssertEqual(response.method, "mail.draft.create.v1")
    XCTAssertEqual(response.result?["draft_created"], .boolean(true))
    XCTAssertEqual(mail.calls, 1)

    let invalid = broker.handle(
      try request(
        .mailDraftCreate,
        args: [
          "recipient": .string("claudio@aisosu.fi"),
          "subject": .string(""),
          "body": .string("Draft only"),
        ]
      )
    )

    XCTAssertEqual(invalid.error?.code, "invalid_arguments")
    XCTAssertEqual(mail.calls, 1)
  }

  func testBrokerBoundsArgumentsAndRegistryOrder() throws {
    let registry = NativeCapabilityRegistry()
    XCTAssertEqual(registry.definitions.map(\.capability), NativeCapability.allCases)
    var deep: BrokerJSONValue = .string("x")
    for _ in 0..<8 { deep = .array([deep]) }
    XCTAssertThrowsError(
      try NativeCapabilityRequest(
        requestId: "req-1", capability: .contactsStatus, requesterId: "core",
        explicitUserRequest: false, requestLocale: "en", responseLocale: "en",
        arguments: ["nested": deep]))
  }
  func testNativeBrokerSocketIsPrivateEphemeralAndCleansUp() throws {
    let server = try NativeBrokerTransportServer(broker: NativeCapabilityBroker(permission: FakePermission(.granted)))
    XCTAssertFalse(server.token.isEmpty)
    try server.start()
    let mode = try FileManager.default.attributesOfItem(atPath: server.socketURL.path)[.posixPermissions] as? NSNumber
    XCTAssertEqual((mode?.intValue ?? 0) & 0o777, 0o600)
    XCTAssertTrue(FileManager.default.fileExists(atPath: server.socketURL.path))
    server.stop()
    XCTAssertFalse(FileManager.default.fileExists(atPath: server.socketURL.path))
  }
  func testNativeBrokerServesAuthenticatedSequentialConnections() throws {
    let server = try NativeBrokerTransportServer(
      broker: NativeCapabilityBroker(permission: FakePermission(.granted)))
    try server.start()
    defer { server.stop() }
    for _ in 0..<2 {
      let request = try request(.contactsStatus)
      let envelope = NativeBrokerTransportEnvelope(token: server.token, request: request)
      let payload = try JSONEncoder().encode(envelope) + Data("\n".utf8)
      let client = try connectToBroker(server.socketURL)
      defer { close(client) }
      XCTAssertEqual(payload.withUnsafeBytes { send(client, $0.baseAddress, payload.count, 0) }, payload.count)
      var response = Data()
      var buffer = [UInt8](repeating: 0, count: 2048)
      while !response.contains(10) {
        let count = recv(client, &buffer, buffer.count, 0)
        XCTAssertGreaterThan(count, 0)
        response.append(buffer, count: count)
      }
      let decoded = try JSONDecoder().decode(
        NativeCapabilityResponse.self,
        from: response.prefix { $0 != 10 })
      XCTAssertEqual(decoded.outcome, .success)
      XCTAssertEqual(decoded.capability, .contactsStatus)
    }
  }
  private func request(_ capability: NativeCapability, args: [String: BrokerJSONValue] = [:]) throws
    -> NativeCapabilityRequest
  {
    try NativeCapabilityRequest(
      requestId: "req-1", capability: capability, requesterId: "core", explicitUserRequest: true,
      requestLocale: "en", responseLocale: "en", arguments: args)
  }
  func testHealthPolicyRetriesRefusedThenSucceeds() {
    let p = CoreHealthPolicy()
    XCTAssertEqual(
      p.nextResult(processRunning: true, elapsedMilliseconds: 0, probeHealthy: false), .retry)
    XCTAssertEqual(
      p.nextResult(processRunning: true, elapsedMilliseconds: 350, probeHealthy: true), .healthy)
  }
  func testHealthPolicyProcessExitAndTimeout() {
    let p = CoreHealthPolicy()
    XCTAssertEqual(
      p.nextResult(processRunning: false, elapsedMilliseconds: 10, probeHealthy: false),
      .processExited)
    XCTAssertEqual(
      p.nextResult(processRunning: true, elapsedMilliseconds: 15_000, probeHealthy: false),
      .timedOut)
  }
  func testHealthPolicyBoundsAndLifecycleGates() {
    let p = CoreHealthPolicy()
    XCTAssertGreaterThanOrEqual(p.timeoutMilliseconds, 10_000)
    XCTAssertGreaterThan(p.retryMilliseconds, 0)
    let rules = CoreLifecycleRules()
    XCTAssertFalse(rules.canStart(ownedProcessExists: true))
    XCTAssertTrue(rules.canStop(ownedProcessExists: true))
    XCTAssertEqual(rules.stateAfterLaunchFailure(), .unavailable)
  }
  func testBoundedDiagnosticTailsAndSanitization() {
    let text = (0..<40).map { "line\($0)\u{001b}[31m" }.joined(separator: "\n")
    XCTAssertEqual(boundedDiagnosticTail(text, maxLines: 30).count, 30)
    XCTAssertFalse(
      boundedDiagnosticTail("bad\u{0007}line", maxLines: 10)[0].unicodeScalars.contains {
        $0.value < 0x20
      })
    XCTAssertLessThanOrEqual(sanitizedDiagnosticLine(String(repeating: "x", count: 500)).count, 240)
    XCTAssertEqual(
      boundedDiagnosticTail((0..<20).map { "out\($0)" }.joined(separator: "\n"), maxLines: 10)
        .count, 10)
  }
  func testContactLabelNormalizationRemovesAppleTokens() {
    let gateway = NativeContactsDataGateway(permission: FakePermission(.granted))
    XCTAssertEqual(gateway.normalizeContactLabel(CNLabelPhoneNumberMobile as NSString), "mobile")
    XCTAssertEqual(gateway.normalizeContactLabel("*$!<Mobile>!$*" as NSString), "Mobile")
    XCTAssertEqual(gateway.normalizeContactLabel("custom" as NSString), "custom")
  }
  func testContactReferencesAreStableDistinctAndNeverEmpty() {
    let gateway = NativeContactsDataGateway(permission: FakePermission(.granted))
    let first = try! XCTUnwrap(gateway.opaqueReference(for: "native-contact-1"))
    XCTAssertEqual(first, gateway.opaqueReference(for: "native-contact-1"))
    XCTAssertNotEqual(first, gateway.opaqueReference(for: "native-contact-2"))
    XCTAssertTrue(first.hasPrefix("contact_"))
    XCTAssertNil(gateway.opaqueReference(for: ""))
  }
  func testLaunchSnapshotCapturesProcessConfiguration() throws {
    let root = try repository()
    let config = try RepositoryConfiguration.validate(root)
    let process = Process()
    process.executableURL = config.executable
    process.arguments = [
      "-m", "uvicorn", "cauco_core.main:app", "--host", "127.0.0.1", "--port", "8765",
    ]
    process.currentDirectoryURL = config.repository
    let snapshot = CoreLaunchDiagnosticSnapshot(
      process: process,
      configuration: CoreLaunchConfiguration(
        executable: config.executable, repository: config.repository), state: .starting)
    XCTAssertEqual(snapshot.executable, config.executable)
    XCTAssertEqual(snapshot.workingDirectory, config.repository)
    XCTAssertEqual(snapshot.arguments, process.arguments)
    XCTAssertEqual(snapshot.lifecycleState, .starting)
  }

  func testCalendarSanitizerRemovesControlsPreservesUnicodeAndBounds() {
    XCTAssertEqual(calendarSanitized("A\u{0000}B\u{001F}C\u{007F}D\u{0085}é ☕", limit: 100), "ABCDé ☕")
    XCTAssertEqual(calendarSanitized("abcdef", limit: 3), "abc")
  }

  func testCalendarISO8601DateAcceptsSupportedFormsAndRejectsInvalidForms() {
    XCTAssertNotNil(calendarISO8601Date("2026-08-09T00:00:00+03:00"))
    XCTAssertNotNil(calendarISO8601Date("2026-08-09T00:00:00.123+03:00"))
    XCTAssertNotNil(calendarISO8601Date("2026-08-09T00:00:00Z"))
    XCTAssertNil(calendarISO8601Date("2026-08-09T00:00:00"))
    XCTAssertNil(calendarISO8601Date("not-a-date"))
  }

  func testCalendarISO8601RangeInvariants() {
    let start = calendarISO8601Date("2026-08-09T00:00:00+03:00")!
    XCTAssertEqual(start, calendarISO8601Date("2026-08-09T00:00:00+03:00"))
    XCTAssertGreaterThan(start.addingTimeInterval(1), start)
    XCTAssertLessThan(start, start.addingTimeInterval(31 * 86400))
    XCTAssertGreaterThan(start.addingTimeInterval(31 * 86400 + 1), start)
  }
}

private func connectToBroker(_ url: URL) throws -> Int32 {
  let client = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
  guard client >= 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
  var address = sockaddr_un()
  address.sun_family = sa_family_t(AF_UNIX)
  let capacity = MemoryLayout<sockaddr_un>.size - MemoryLayout<sa_family_t>.size
  withUnsafeMutablePointer(to: &address.sun_path) { pointer in
    pointer.withMemoryRebound(to: CChar.self, capacity: capacity) { cPath in
      url.path.withCString { path in strncpy(cPath, path, capacity - 1) }
    }
  }
  let length = socklen_t(MemoryLayout<sa_family_t>.size + url.path.utf8.count + 1)
  let result = withUnsafePointer(to: &address) { pointer in
    pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
      Darwin.connect(client, $0, length)
    }
  }
  guard result == 0 else { close(client); throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
  return client
}

private final class FakeMailMessageGateway: MailMessageGateway, @unchecked Sendable {
  var calls = 0
  var lastLimit: Int?

  func listMessages(limit: Int) throws -> [String: BrokerJSONValue] {
    calls += 1
    lastLimit = limit

    return [
      "results": .array([
        .object([
          "message_reference": .string("mailmsg_0123456789abcdef"),
          "sender": .string("Sender <sender@example.com>"),
          "subject": .string("Subject"),
          "date_received": .string("2026-08-21T05:00:00.000Z"),
          "read": .boolean(false),
        ])
      ]),
      "result_count": .number(1),
      "truncated": .boolean(false),
    ]
  }
}

private final class FakeMailAccountGateway: MailAccountGateway, @unchecked Sendable {
  let accountReference = "mailacct_0123456789abcdef"
  var accountCalls = 0
  var mailboxCalls = 0

  func listAccounts() throws -> [String: BrokerJSONValue] {
    accountCalls += 1
    return [
      "results": .array([
        .object([
          "account_reference": .string(accountReference),
          "name": .string("Personal"),
          "email_addresses": .array([.string("user@example.com")]),
        ])
      ]),
      "result_count": .number(1),
      "truncated": .boolean(false),
    ]
  }

  func listMailboxes(accountReference: String) throws -> [String: BrokerJSONValue] {
    mailboxCalls += 1
    guard accountReference == self.accountReference else {
      throw BrokerError.mailAccountReferenceUnknown
    }
    return [
      "results": .array([
        .object([
          "mailbox_reference": .string("mailbox_0123456789abcdef"),
          "name": .string("Inbox"),
        ])
      ]),
      "result_count": .number(1),
      "truncated": .boolean(false),
    ]
  }
}

private final class FakeMailDraftGateway: MailDraftGateway, @unchecked Sendable {
  var calls = 0

  func createDraft(
    recipient: String,
    subject: String,
    body: String
  ) throws -> [String: BrokerJSONValue] {
    calls += 1
    return [
      "recipient": .string(recipient),
      "subject": .string(subject),
      "draft_created": .boolean(true),
    ]
  }
}

private final class FakePermission: ContactsPermissionGateway {
  let state: ContactsAuthorization
  var requests = 0
  init(_ state: ContactsAuthorization) { self.state = state }
  func authorizationState() -> ContactsAuthorization { state }
  func requestAccess(completion: @escaping (ContactsAuthorization) -> Void) {
    requests += 1
    completion(state)
  }
}

private final class FakeCalendarPermission: CalendarPermissionGateway {
  let state: CalendarAuthorization
  var requests = 0
  var dataReads = 0
  init(_ state: CalendarAuthorization) { self.state = state }
  func authorizationState() -> CalendarAuthorization { state }
  func requestAccess(completion: @escaping (CalendarAuthorization) -> Void) {
    requests += 1
    completion(.granted)
  }
}

private struct InertContactsDataGateway: ContactsDataGateway {
  func search(query: String, limit: Int) throws -> [String: BrokerJSONValue] {
    ["results": .array([]), "result_count": .number(0), "truncated": .boolean(false)]
  }
  func get(contactReference: String) throws -> [String: BrokerJSONValue] { [:] }
  func listLimited(limit: Int) throws -> [String: BrokerJSONValue] { ["results": .array([]), "result_count": .number(0), "truncated": .boolean(false)] }
}
