import Foundation
import XCTest

@testable import CaucoHostCore

final class WakeWordCapabilityTests: XCTestCase {
  func testStatusReportsUnavailableWithoutStartingDetector() throws {
    let detector = FakeWakeWordDetector(available: false)
    let response = broker(detector: detector).handle(try request(.wakewordStatus))

    XCTAssertEqual(response.outcome, .success)
    XCTAssertEqual(response.result?["available"], .boolean(false))
    XCTAssertEqual(response.result?["state"], .string("unavailable"))
    XCTAssertEqual(response.result?["permission_status"], .string("unavailable"))
    XCTAssertEqual(response.result?["detector_backend"], .string("test_native_wakeword"))
    XCTAssertEqual(response.result?["phrase_key"], .null)
    XCTAssertEqual(response.result?["active"], .boolean(false))
    XCTAssertEqual(detector.startCalls, 0)
  }

  func testStartRequiresExplicitUserRequestAndRejectsUnavailableDetector() throws {
    let detector = FakeWakeWordDetector(available: false)
    let nativeBroker = broker(detector: detector)
    let arguments = validStartArguments()

    let implicit = nativeBroker.handle(
      try request(.wakewordStart, args: arguments, explicitUserRequest: false))
    XCTAssertEqual(implicit.outcome, .rejected)
    XCTAssertEqual(implicit.error, .permissionNotRequested)

    let unavailable = nativeBroker.handle(try request(.wakewordStart, args: arguments))
    XCTAssertEqual(unavailable.outcome, .unavailable)
    XCTAssertEqual(unavailable.error, .capabilityUnavailable)
    XCTAssertEqual(unavailable.result?["accepted"], .boolean(false))
    XCTAssertEqual(unavailable.result?["active"], .boolean(false))
    XCTAssertEqual(detector.startCalls, 0)
  }

  func testStopIsSafeAndIdempotent() throws {
    let detector = FakeWakeWordDetector()
    let nativeBroker = broker(detector: detector)

    XCTAssertEqual(
      nativeBroker.handle(try request(.wakewordStop)).result?["state"], .string("stopped"))
    XCTAssertEqual(
      nativeBroker.handle(try request(.wakewordStop)).result?["active"], .boolean(false))
    XCTAssertEqual(detector.stopCalls, 2)
  }

  func testStartArgumentsFailClosed() throws {
    let detector = FakeWakeWordDetector()
    let nativeBroker = broker(detector: detector)
    let invalidArguments: [[String: BrokerJSONValue]] = [
      [:],
      ["phrase_key": .string("hola_cauco")],
      ["phrase_key": .string("unknown"), "locale": .string("es-ES")],
      ["phrase_key": .string("hola_cauco"), "locale": .string("en-US")],
      ["phrase_key": .string("hola_cauco"), "locale": .string("es-es")],
      [
        "phrase_key": .string("hola_cauco"), "locale": .string("es-ES"),
        "raw_pcm": .array([]),
      ],
      [
        "phrase_key": .string("hola_cauco"), "locale": .string("es-ES"),
        "model_path": .string("/tmp/model.mlmodel"),
      ],
    ]

    for arguments in invalidArguments {
      let response = nativeBroker.handle(try request(.wakewordStart, args: arguments))
      XCTAssertEqual(response.outcome, .rejected)
      XCTAssertEqual(response.error, .invalidArguments)
    }
    XCTAssertEqual(detector.startCalls, 0)
  }

  func testFakeDetectorEmitsOneEventAfterStoppingListening() throws {
    let recorder = WakeWordTestRecorder()
    let detector = FakeWakeWordDetector(order: { recorder.recordOrder($0) })
    let service = WakeWordCapabilityService(
      detector: detector,
      eventHandler: {
        recorder.recordOrder("event")
        recorder.recordEvent($0)
      },
      now: { Date(timeIntervalSince1970: 123) },
      makeEventReference: { "wakeevt_test" })

    let configuration = WakeWordDetectorConfiguration(phraseKey: "hola_cauco", locale: "es-ES")
    try service.start(configuration: configuration)
    detector.detect(confidence: 0.91)
    detector.detect(confidence: 0.92)

    XCTAssertEqual(recorder.events.count, 1)
    XCTAssertEqual(recorder.events.first?.eventReference, "wakeevt_test")
    XCTAssertEqual(recorder.events.first?.phraseKey, "hola_cauco")
    XCTAssertEqual(recorder.events.first?.confidence, 0.91)
    XCTAssertEqual(recorder.order, ["start", "stop", "event"])
    XCTAssertEqual(service.status().state, .detected)
    XCTAssertFalse(service.status().active)
  }

  func testStaleDetectionAfterStopOrNewStartIsIgnored() throws {
    let recorder = WakeWordTestRecorder()
    let detector = FakeWakeWordDetector()
    let service = WakeWordCapabilityService(detector: detector) { recorder.recordEvent($0) }
    let configuration = WakeWordDetectorConfiguration(phraseKey: "hola_cauco", locale: "es")

    try service.start(configuration: configuration)
    let stale = detector.handlers[0]
    service.stop()
    stale(WakeWordDetectionSignal())
    XCTAssertTrue(recorder.events.isEmpty)

    try service.start(configuration: configuration)
    stale(WakeWordDetectionSignal())
    XCTAssertTrue(recorder.events.isEmpty)
    detector.detect()
    XCTAssertEqual(recorder.events.count, 1)
  }

  func testBrokerShutdownStopsActiveDetectorAndInvalidatesCallbacks() throws {
    let recorder = WakeWordTestRecorder()
    let detector = FakeWakeWordDetector()
    let nativeBroker = broker(detector: detector) { recorder.recordEvent($0) }
    let started = nativeBroker.handle(
      try request(.wakewordStart, args: validStartArguments()))
    XCTAssertEqual(started.result?["accepted"], .boolean(true))
    XCTAssertEqual(started.result?["active"], .boolean(true))
    let callback = detector.handlers[0]

    nativeBroker.shutdown()
    callback(WakeWordDetectionSignal())

    XCTAssertGreaterThanOrEqual(detector.stopCalls, 1)
    XCTAssertTrue(recorder.events.isEmpty)
    XCTAssertEqual(
      nativeBroker.handle(try request(.wakewordStatus)).result?["active"], .boolean(false))
  }

  func testRepeatedStartDoesNotCreateAnotherDetectorAndRejectsConfigurationChange() throws {
    let detector = FakeWakeWordDetector()
    let service = WakeWordCapabilityService(detector: detector)
    let configuration = WakeWordDetectorConfiguration(phraseKey: "hola_cauco", locale: "es-ES")

    try service.start(configuration: configuration)
    try service.start(configuration: configuration)
    XCTAssertEqual(detector.startCalls, 1)
    XCTAssertThrowsError(
      try service.start(
        configuration: WakeWordDetectorConfiguration(phraseKey: "different", locale: "es-ES")))
    XCTAssertEqual(detector.startCalls, 1)
  }

  func testRegistryExposesOnlyNarrowWakeWordSurface() {
    let wakeCapabilities = NativeCapabilityRegistry().definitions.filter {
      $0.capability.rawValue.hasPrefix("wakeword.")
    }

    XCTAssertEqual(
      wakeCapabilities.map(\.capability), [.wakewordStatus, .wakewordStart, .wakewordStop])
    XCTAssertEqual(
      Set(wakeCapabilities.map(\.permissionId)), Set(["macos.microphone.wakeword"]))
    let capabilityNames = Set(NativeCapability.allCases.map(\.rawValue))
    for forbidden in ["microphone.read", "audio.stream", "raw_pcm", "audio.files"] {
      XCTAssertFalse(capabilityNames.contains(forbidden))
    }
  }

  func testWakeWordModelsContainNoRawAudioOrFilesystemInputs() throws {
    let source = try String(
      contentsOf: sourceRoot().appendingPathComponent(
        "Sources/CaucoHostCore/WakeWordDetectorGateway.swift"), encoding: .utf8)
    for forbidden in ["AVAudioPCMBuffer", "Data", "URL", "modelPath", "audioFile"] {
      XCTAssertFalse(source.contains(forbidden), "Unexpected generic input: \(forbidden)")
    }
  }

  private func broker(
    detector: WakeWordDetectorGateway,
    eventHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void = { _ in }
  ) -> NativeCapabilityBroker {
    NativeCapabilityBroker(
      permission: WakeWordInertContactsPermission(), wakeWordDetector: detector,
      wakeWordEventHandler: eventHandler)
  }

  private func request(
    _ capability: NativeCapability, args: [String: BrokerJSONValue] = [:],
    explicitUserRequest: Bool = true
  ) throws -> NativeCapabilityRequest {
    try NativeCapabilityRequest(
      requestId: "wake-test", capability: capability, requesterId: "core",
      explicitUserRequest: explicitUserRequest, requestLocale: "es-ES", responseLocale: "en",
      arguments: args)
  }

  private func validStartArguments() -> [String: BrokerJSONValue] {
    ["phrase_key": .string("hola_cauco"), "locale": .string("es-ES")]
  }

  private func sourceRoot() -> URL {
    URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
      .deletingLastPathComponent()
  }
}

private final class FakeWakeWordDetector: WakeWordDetectorGateway, @unchecked Sendable {
  let availability: WakeWordDetectorAvailability
  private(set) var handlers: [@Sendable (WakeWordDetectionSignal) -> Void] = []
  private(set) var startCalls = 0
  private(set) var stopCalls = 0
  private let order: @Sendable (String) -> Void

  init(available: Bool = true, order: @escaping @Sendable (String) -> Void = { _ in }) {
    availability = WakeWordDetectorAvailability(
      available: available, backendIdentifier: "test_native_wakeword",
      permissionStatus: available ? .granted : .unavailable)
    self.order = order
  }

  func start(
    configuration _: WakeWordDetectorConfiguration,
    detectionHandler: @escaping @Sendable (WakeWordDetectionSignal) -> Void
  ) throws {
    startCalls += 1
    handlers.append(detectionHandler)
    order("start")
  }

  func stop() {
    stopCalls += 1
    order("stop")
  }

  func detect(confidence: Double? = nil) {
    handlers.last?(WakeWordDetectionSignal(confidence: confidence))
  }
}

private final class WakeWordTestRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var storedEvents: [WakeWordDetectedEvent] = []
  private var storedOrder: [String] = []

  var events: [WakeWordDetectedEvent] {
    lock.lock()
    defer { lock.unlock() }
    return storedEvents
  }

  var order: [String] {
    lock.lock()
    defer { lock.unlock() }
    return storedOrder
  }

  func recordEvent(_ event: WakeWordDetectedEvent) {
    lock.lock()
    storedEvents.append(event)
    lock.unlock()
  }

  func recordOrder(_ value: String) {
    lock.lock()
    storedOrder.append(value)
    lock.unlock()
  }
}

private final class WakeWordInertContactsPermission: ContactsPermissionGateway {
  func authorizationState() -> ContactsAuthorization { .unavailable }
  func requestAccess(completion: @escaping (ContactsAuthorization) -> Void) {
    completion(.unavailable)
  }
}
