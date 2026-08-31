import XCTest
@testable import CaucoHostCore

final class HostRuntimeContractsTests: XCTestCase {
  func testFakeFactoryReceivesIndependentCoreAndLocalWakeCallbacks() throws {
    let factory = FakeBrokerFactory()
    let server = try factory.makeBrokerServer(
      coreWakeHandler: { _ in factory.recorder.core += 1 },
      localWakeHandler: { _ in factory.recorder.local += 1 })
    try server.start()
    factory.recorder.coreHandler?(sampleEvent)
    factory.recorder.localHandler?(sampleEvent)
    server.stop()
    XCTAssertEqual(factory.recorder.core, 1)
    XCTAssertEqual(factory.recorder.local, 1)
    XCTAssertEqual((server as? FakeBrokerServer)?.starts, 1)
    XCTAssertEqual((server as? FakeBrokerServer)?.stops, 1)
  }

  func testProductionBrokerServerConformsToContract() {
    XCTAssertTrue(NativeBrokerTransportServer.self is HostRuntimeBrokerServer.Type)
  }

  private var sampleEvent: WakeWordDetectedEvent {
    WakeWordDetectedEvent(eventReference: "wakeevt_test", phraseKey: "hola_cauco", detectedAt: Date(), confidence: 0.9)
  }
}

private final class WakeCallbackRecorder: @unchecked Sendable {
  var core = 0
  var local = 0
  var coreHandler: ((WakeWordDetectedEvent) -> Void)?
  var localHandler: ((WakeWordDetectedEvent) -> Void)?
}

private final class FakeBrokerFactory: HostRuntimeBrokerFactory {
  func makeBrokerServer(
    coreWakeHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void,
    localWakeHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void
  ) throws -> HostRuntimeBrokerServer {
    let server = FakeBrokerServer()
    recorder.coreHandler = coreWakeHandler
    recorder.localHandler = localWakeHandler
    return server
  }
  let recorder = WakeCallbackRecorder()
}

private final class FakeBrokerServer: HostRuntimeBrokerServer {
  var starts = 0
  var stops = 0
  func start() throws { starts += 1 }
  func stop() { stops += 1 }
}
