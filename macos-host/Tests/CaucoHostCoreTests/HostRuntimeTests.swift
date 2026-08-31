import XCTest
@testable import CaucoHostCore

@MainActor
final class HostRuntimeTests: XCTestCase {
  func testConstructionHasNoSideEffectsAndStartIsIdempotent() {
    let processFactory = TestProcessFactory()
    let brokerFactory = TestBrokerFactory()
    let runtime = HostRuntime(configuration: configuration(), processFactory: processFactory, brokerFactory: brokerFactory)

    XCTAssertEqual(processFactory.created, 0)
    XCTAssertEqual(brokerFactory.created, 0)
    runtime.start(); runtime.start()
    XCTAssertEqual(processFactory.created, 1)
    XCTAssertEqual(processFactory.process.launches, 1)
    XCTAssertEqual(brokerFactory.created, 1)
    XCTAssertEqual(brokerFactory.server.starts, 1)
    runtime.stop(); runtime.stop()
    XCTAssertEqual(brokerFactory.server.stops, 1)
  }

  func testShutdownIsTerminalAndIdempotent() {
    let processFactory = TestProcessFactory(); let brokerFactory = TestBrokerFactory()
    let runtime = HostRuntime(configuration: configuration(), processFactory: processFactory, brokerFactory: brokerFactory)
    runtime.start(); runtime.shutdown(); runtime.shutdown(); runtime.start()
    XCTAssertTrue(runtime.isShutdown)
    XCTAssertEqual(processFactory.created, 1)
    XCTAssertEqual(processFactory.process.terminations, 1)
    XCTAssertEqual(brokerFactory.server.stops, 1)
  }

  func testBrokerReceivesIndependentCoreAndLocalWakeHandlers() {
    let processFactory = TestProcessFactory(); let brokerFactory = TestBrokerFactory()
    var localEvents = 0
    let runtime = HostRuntime(configuration: configuration(), processFactory: processFactory, brokerFactory: brokerFactory,
                              localWakeHandler: { _ in localEvents += 1 })
    runtime.start()
    let event = WakeWordDetectedEvent(eventReference: "test", phraseKey: "hola_cauco", detectedAt: Date(), confidence: 0.9)
    brokerFactory.coreHandler?(event); brokerFactory.localHandler?(event)
    XCTAssertEqual(localEvents, 1)
    runtime.shutdown()
  }

  private func configuration() -> HostRuntimeConfiguration {
    HostRuntimeConfiguration(executable: URL(fileURLWithPath: "/tmp/core"), arguments: ["--test"],
                             workingDirectory: URL(fileURLWithPath: "/tmp"), coreBaseURL: URL(string: "http://127.0.0.1:8765")!)
  }
}

private final class TestProcessFactory: HostRuntimeProcessFactory {
  let process = TestProcess(); var created = 0
  func makeProcess(configuration: HostRuntimeConfiguration) throws -> HostRuntimeProcess { created += 1; return process }
}

private final class TestProcess: HostRuntimeProcess {
  var isRunning = false; let processIdentifier: Int32 = 101; var diagnosticWorkingDirectory: URL? = URL(fileURLWithPath: "/tmp")
  var launches = 0; var terminations = 0; private var termination: (() -> Void)?
  func configure(configuration: HostRuntimeConfiguration) throws { diagnosticWorkingDirectory = configuration.workingDirectory }
  func onTermination(_ handler: @escaping @Sendable () -> Void) { termination = handler }
  func launch() throws { launches += 1; isRunning = true }
  func terminate() { terminations += 1; isRunning = false; termination?() }
  func waitUntilExit() {}
}

private final class TestBrokerFactory: HostRuntimeBrokerFactory {
  let server = TestBroker(); var created = 0
  var coreHandler: ((WakeWordDetectedEvent) -> Void)?; var localHandler: ((WakeWordDetectedEvent) -> Void)?
  func makeBrokerServer(coreWakeHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void,
                        localWakeHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void) throws -> HostRuntimeBrokerServer {
    created += 1; coreHandler = coreWakeHandler; localHandler = localWakeHandler; return server
  }
}

private final class TestBroker: HostRuntimeBrokerServer { var starts = 0; var stops = 0; func start() throws { starts += 1 }; func stop() { stops += 1 } }
