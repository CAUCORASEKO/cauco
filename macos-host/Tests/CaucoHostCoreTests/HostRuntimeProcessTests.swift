import XCTest
@testable import CaucoHostCore

final class HostRuntimeProcessTests: XCTestCase {
  func testFakeProcessRecordsConfigureTerminationBeforeLaunch() throws {
    let process = FakeRuntimeProcess()
    let configuration = HostRuntimeConfiguration(
      executable: URL(fileURLWithPath: "/tmp/python"),
      arguments: ["-m", "cauco_core.main"],
      workingDirectory: URL(fileURLWithPath: "/tmp/repo"),
      environment: ["TEST": "1"],
      coreBaseURL: URL(string: "http://127.0.0.1:8765")!)
    try process.configure(configuration: configuration)
    process.onTermination {}
    try process.launch()
    XCTAssertEqual(process.order, ["configure", "termination", "launch"])
    XCTAssertEqual(process.configuration?.arguments, configuration.arguments)
    XCTAssertEqual(process.configuration?.environment, configuration.environment)
  }

  func testProductionProcessConformsToLaunchContract() {
    let process: HostRuntimeProcess = Process()
    XCTAssertEqual(process.processIdentifier, 0)
    XCTAssertFalse(process.isRunning)
  }
}

private final class FakeRuntimeProcess: HostRuntimeProcess {
  var isRunning = false
  let processIdentifier: Int32 = 7
  var diagnosticWorkingDirectory: URL?
  var configuration: HostRuntimeConfiguration?
  var order: [String] = []
  func configure(configuration: HostRuntimeConfiguration) throws {
    self.configuration = configuration; diagnosticWorkingDirectory = configuration.workingDirectory; order.append("configure")
  }
  func onTermination(_ handler: @escaping @Sendable () -> Void) { order.append("termination") }
  func launch() throws { order.append("launch"); isRunning = true }
  func terminate() { isRunning = false }
  func waitUntilExit() {}
}
