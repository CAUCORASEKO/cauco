import XCTest
import Contacts
@testable import CaucoHostCore

final class HostCoreTests: XCTestCase {
    func testAuthorizationMapping() { XCTAssertEqual(NativeContactsPermissionGateway.map(.notDetermined), .notRequested); XCTAssertEqual(NativeContactsPermissionGateway.map(.denied), .denied); XCTAssertEqual(NativeContactsPermissionGateway.map(.restricted), .restricted) }
    func testFixedProcessArgumentsAndLocalURL() { let c = CoreLaunchConfiguration(executable: URL(fileURLWithPath: "/tmp/python"), repository: URL(fileURLWithPath: "/tmp/repo")); XCTAssertEqual(c.arguments, ["-m", "uvicorn", "cauco_core.main:app", "--host", "127.0.0.1", "--port", "8765"]); XCTAssertTrue(isLocalCoreURL(c.url)); XCTAssertFalse(c.arguments.contains(where: { $0.contains(";") })) }
    func testBoundedDiagnostics() { XCTAssertEqual(boundedDiagnostic(String(repeating: "x", count: 10), limit: 4).count, 4) }
}
