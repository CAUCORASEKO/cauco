import XCTest
@testable import CaucoHost

@MainActor
final class ConversationTests: XCTestCase {
  func testHostOwnsOneSharedPresentationAndController() {
    let host = HostModel()
    XCTAssertTrue(host.conversationInteraction.presentation === host.conversationPresentation)
  }

  func testSubmitUsesOneRequestAndPreservesPayload() async {
    let transport = FakeConversationTransport()
    let presentation = ConversationPresentationModel()
    let controller = ConversationInteractionController(presentation: presentation, transport: transport)
    presentation.inputText = "  plan this  "
    controller.submit()
    await transport.waitForRequestCount(1)
    XCTAssertEqual(transport.requests.count, 1)
    XCTAssertEqual(transport.requests[0].instruction, "plan this")
    XCTAssertTrue(transport.requests[0].useReasoning)
    transport.completeNext(with: "Done")
    await waitUntil { presentation.state == .complete }
    XCTAssertEqual(presentation.response, "Done")
    XCTAssertEqual(presentation.inputText, "")
  }

  func testErrorIsBoundedAndClearsLoading() async {
    let transport = FakeConversationTransport()
    let presentation = ConversationPresentationModel()
    let controller = ConversationInteractionController(presentation: presentation, transport: transport)
    presentation.inputText = "plan"
    controller.submit(); await transport.waitForRequestCount(1); transport.completeNext(with: TestError.failed)
    await waitUntil { presentation.state == .error }
    XCTAssertEqual(presentation.error, "Advisory planning is unavailable. No action was taken.")
  }

  func testNewerRequestWinsAndCancellationIsNotAnError() async {
    let transport = FakeConversationTransport()
    let presentation = ConversationPresentationModel()
    let controller = ConversationInteractionController(presentation: presentation, transport: transport)
    presentation.inputText = "A"; controller.submit(); await transport.waitForRequestCount(1)
    controller.cancel(); presentation.inputText = "B"; controller.submit(); await transport.waitForRequestCount(2)
    transport.complete(request: 0, with: "old")
    transport.complete(request: 0, with: "new")
    await waitUntil { presentation.state == .complete }
    XCTAssertEqual(presentation.response, "new")
    XCTAssertTrue(presentation.error.isEmpty)
  }

  func testEmptyInputDoesNotRequest() {
    let transport = FakeConversationTransport()
    let presentation = ConversationPresentationModel()
    let controller = ConversationInteractionController(presentation: presentation, transport: transport)
    presentation.inputText = "  \n  "; controller.submit()
    XCTAssertTrue(transport.requests.isEmpty)
    XCTAssertEqual(presentation.state, .idle)
  }

  private func waitUntil(_ condition: @escaping () -> Bool) async {
    for _ in 0..<100 where !condition() { try? await Task.sleep(for: .milliseconds(1)) }
  }
}

@MainActor
private final class FakeConversationTransport: ConversationTransport {
  struct Pending { let continuation: CheckedContinuation<String, Error> }
  struct Request: Equatable { let instruction: String; let useReasoning: Bool }
  var requests: [Request] = []
  var pending: [Pending] = []
  func respond(instruction: String, useReasoning: Bool) async throws -> String {
    requests.append(Request(instruction: instruction, useReasoning: useReasoning))
    return try await withCheckedThrowingContinuation { pending.append(Pending(continuation: $0)) }
  }
  func waitForRequestCount(_ count: Int) async {
    for _ in 0..<100 where requests.count < count { await Task.yield() }
  }
  func completeNext(with value: String) { complete(request: 0, with: .success(value)) }
  func completeNext(with error: Error) { complete(request: 0, with: .failure(error)) }
  func complete(request index: Int, with result: Result<String, Error>) {
    guard index < pending.count else { return }
    let item = pending.remove(at: index)
    item.continuation.resume(with: result)
  }
  func complete(request index: Int, with value: String) { complete(request: index, with: .success(value)) }
}

private enum TestError: Error { case failed }
