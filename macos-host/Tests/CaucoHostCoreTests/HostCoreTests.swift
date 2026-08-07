import XCTest
import Contacts
@testable import CaucoHostCore

final class HostCoreTests: XCTestCase {
    func testAuthorizationMapping() { XCTAssertEqual(NativeContactsPermissionGateway.map(.notDetermined), .notRequested); XCTAssertEqual(NativeContactsPermissionGateway.map(.denied), .denied); XCTAssertEqual(NativeContactsPermissionGateway.map(.restricted), .restricted) }
    func testFixedProcessArgumentsAndLocalURL() { let c = CoreLaunchConfiguration(executable: URL(fileURLWithPath: "/tmp/python"), repository: URL(fileURLWithPath: "/tmp/repo")); XCTAssertEqual(c.arguments, ["-m", "uvicorn", "cauco_core.main:app", "--host", "127.0.0.1", "--port", "8765"]); XCTAssertTrue(isLocalCoreURL(c.url)); XCTAssertFalse(c.arguments.contains(where: { $0.contains(";") })) }
    func testLocalhostOnlyAndHealthPath() { XCTAssertFalse(isLocalCoreURL(URL(string: "http://localhost:8765")!)); XCTAssertEqual(URL(string: "http://127.0.0.1:8765")!.appendingPathComponent("health").absoluteString, "http://127.0.0.1:8765/health") }
    func testRepositoryRelativeVirtualenvResolution() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let python = root.appendingPathComponent(".venv/bin/python"); try FileManager.default.createDirectory(at: python.deletingLastPathComponent(), withIntermediateDirectories: true); FileManager.default.createFile(atPath: python.path, contents: Data()); try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: python.path)
        let result = try resolveCorePython(repository: root, environment: [:]); XCTAssertEqual(result.executable, python.standardizedFileURL)
    }
    func testMissingAndNonExecutableResolution() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString); try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        XCTAssertThrowsError(try resolveCorePython(repository: root, environment: [:])) { XCTAssertEqual($0 as? CoreExecutableResolutionError, .missing(root.appendingPathComponent(".venv/bin/python"))) }
        let python = root.appendingPathComponent(".venv/bin/python"); try FileManager.default.createDirectory(at: python.deletingLastPathComponent(), withIntermediateDirectories: true); FileManager.default.createFile(atPath: python.path, contents: Data()); try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: python.path)
        XCTAssertThrowsError(try resolveCorePython(repository: root, environment: [:])) { XCTAssertEqual($0 as? CoreExecutableResolutionError, .notExecutable(python)) }
    }
    func testLifecycleRules() { let rules = CoreLifecycleRules(); XCTAssertTrue(rules.canStart(ownedProcessExists: false)); XCTAssertFalse(rules.canStart(ownedProcessExists: true)); XCTAssertEqual(rules.stateAfterLaunchFailure(), .unavailable); XCTAssertEqual(rules.stateAfterStartupTimeout(), .unavailable); XCTAssertTrue(rules.canStop(ownedProcessExists: true)); XCTAssertFalse(rules.canStop(ownedProcessExists: false)) }
    func testNoShellArgumentsAndBoundedDiagnostics() { let c = CoreLaunchConfiguration(executable: URL(fileURLWithPath: "/tmp/python"), repository: URL(fileURLWithPath: "/tmp/repo")); XCTAssertFalse(c.arguments.contains("sh") || c.arguments.contains("zsh")); XCTAssertEqual(boundedDiagnostic(String(repeating: "x", count: 10), limit: 4).count, 4); XCTAssertEqual(boundedDiagnostic(String(repeating: "x", count: 2)).count, 2) }
}
