import ServiceManagement
import XCTest
@testable import CaucoHostCore

final class LaunchAtLoginServiceTests: XCTestCase {
  final class Fake: LaunchAtLoginRegistering {
    var status: SMAppService.Status
    var shouldFail = false
    init(_ status: SMAppService.Status) { self.status = status }
    func register() throws {
      if shouldFail { throw NSError(domain: "test", code: 1) }
      status = .enabled
    }
    func unregister() throws {
      if shouldFail { throw NSError(domain: "test", code: 1) }
      status = .notRegistered
    }
  }

  func testMapsOSStatesAndMutatesOnlyThroughService() {
    let fake = Fake(.notRegistered)
    let service = LaunchAtLoginService(service: fake)
    XCTAssertEqual(service.status, .disabled)
    XCTAssertEqual(service.enable(), .enabled)
    XCTAssertEqual(service.disable(), .disabled)
    fake.status = .requiresApproval
    XCTAssertEqual(service.status, .requiresApproval)
  }

  func testRegistrationFailureIsFailClosed() {
    let fake = Fake(.notRegistered)
    fake.shouldFail = true
    let service = LaunchAtLoginService(service: fake)
    XCTAssertEqual(service.enable(), .failed)
    XCTAssertEqual(service.status, .disabled)
    XCTAssertEqual(service.disable(), .failed)
  }
}
