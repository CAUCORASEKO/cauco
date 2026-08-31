import XCTest
@testable import CaucoHostCore

final class CoreProcessDiagnosticsTests: XCTestCase {
  func testFakeProcessBuildsSnapshotWithoutFoundationProcess() {
    let fake = FakeDiagnosticProcess(pid: 42, running: false, directory: URL(fileURLWithPath: "/tmp/core"))
    let snapshot = CoreLaunchDiagnosticSnapshot(
      process: fake,
      configuration: CoreLaunchConfiguration(
        executable: URL(fileURLWithPath: "/tmp/python"),
        repository: URL(fileURLWithPath: "/tmp/core")),
      state: .unavailable)
    XCTAssertEqual(snapshot.pid, 42)
    XCTAssertFalse(snapshot.running)
    XCTAssertEqual(snapshot.workingDirectory.path, "/tmp/core")
    var updated = snapshot
    updated.terminationReason = "exit"
    updated.terminationStatus = 3
    updated.stderrTail = boundedDiagnosticTail("secret\nsecond", maxLines: 1)
    updated.stdoutTail = boundedDiagnosticTail("first\nsecond", maxLines: 1)
    XCTAssertEqual(updated.terminationReason, "exit")
    XCTAssertEqual(updated.terminationStatus, 3)
    XCTAssertEqual(updated.stderrTail, ["second"])
    XCTAssertEqual(updated.stdoutTail, ["second"])
  }
}

private final class FakeDiagnosticProcess: CoreProcessDiagnostics {
  let processIdentifier: Int32
  let isRunning: Bool
  let diagnosticWorkingDirectory: URL?
  init(pid: Int32, running: Bool, directory: URL?) {
    processIdentifier = pid; isRunning = running; diagnosticWorkingDirectory = directory
  }
}
