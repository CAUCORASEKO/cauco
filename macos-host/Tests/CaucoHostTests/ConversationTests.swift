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

  func testConversationIDsAreStablePerModelAndDistinctAcrossModels() async {
    let transport = FakeConversationTransport()
    let model = ConversationPresentationModel()
    let controller = ConversationInteractionController(presentation: model, transport: transport)
    for index in 1...2 {
      model.inputText = "mensaje \(index)"
      controller.submit()
      await transport.waitForRequestCount(index)
      transport.completeNext(with: "respuesta")
      await waitUntil { model.state == .complete }
    }
    XCTAssertEqual(transport.requests.map(\.conversationID), [model.conversationID, model.conversationID])
    XCTAssertNotEqual(model.conversationID, ConversationPresentationModel().conversationID)
    XCTAssertNil(model.draft)
    XCTAssertNil(model.mutationAction)
  }

  func testActiveDraftUpdatesAndFinalizesWithoutApproval() async {
    let transport = FakeConversationTransport()
    let model = ConversationPresentationModel()
    let controller = ConversationInteractionController(presentation: model, transport: transport)
    // An earlier action must not leave an approval button next to a draft.
    model.mutationAction = MutationAction(state: .pendingReview, reviewID: "old-review")
    await deliver(draftReply(), through: controller, model: model, transport: transport)
    XCTAssertEqual(model.activeDraft?.title, "Resultado / Revisión")
    XCTAssertEqual(model.activeDraft?.target, "prueba.txt")
    XCTAssertEqual(model.activeDraft?.content, "hola")
    XCTAssertEqual(model.activeDraft?.prompt, "¿Está bien o quieres hacer cambios?")
    XCTAssertNil(model.mutationAction, "Only mutationAction renders Aprobar / Confirmar escritura")
    var update = draftReply()
    update.draftContent = "nuevo"
    update.draftDigest = "digest-new"
    await deliver(update, through: controller, model: model, transport: transport)
    XCTAssertEqual(model.activeDraft?.id, "draft-1")
    XCTAssertEqual(model.activeDraft?.content, "nuevo")
    XCTAssertEqual(model.activeDraft?.digest, "digest-new")
    update.draftStatus = "finalized"
    update.planningStatus = "draft_finalized"
    await deliver(update, through: controller, model: model, transport: transport)
    XCTAssertNil(model.activeDraft)
    XCTAssertEqual(model.draft?.id, "draft-1")
    XCTAssertEqual(model.draft?.title, "Archivo finalizado")
    XCTAssertNil(model.draft?.prompt)
    XCTAssertNil(model.mutationAction)
  }

  func testDraftConflictRemainsActiveWithoutDestructiveConfirmation() async {
    let transport = FakeConversationTransport()
    let model = ConversationPresentationModel()
    let controller = ConversationInteractionController(presentation: model, transport: transport)
    var reply = draftReply()
    reply.planningStatus = "draft_conflict"
    reply = ConversationReply(text: "El target ya existe. No se sobrescribió.", planningStatus: reply.planningStatus,
                              draftID: reply.draftID, draftStatus: reply.draftStatus, draftTarget: reply.draftTarget,
                              draftContent: reply.draftContent, draftDigest: reply.draftDigest)
    await deliver(reply, through: controller, model: model, transport: transport)
    XCTAssertNotNil(model.activeDraft)
    XCTAssertTrue(model.draft?.statusText.contains("No se sobrescribió") == true)
    XCTAssertTrue(model.response.contains("No se sobrescribió"))
    XCTAssertNil(model.draft?.prompt)
    XCTAssertNil(model.mutationAction)
    controller.approveMutation()
    controller.confirmMutation()
    XCTAssertNil(model.mutationAction)
  }

  func testPendingReviewRetainsExistingActionUI() async {
    let transport = FakeConversationTransport()
    let model = ConversationPresentationModel()
    let controller = ConversationInteractionController(presentation: model, transport: transport)
    await deliver(ConversationReply(text: "Revisión", reviewID: "review-1", planningStatus: "pending_review"),
                  through: controller, model: model, transport: transport)
    XCTAssertEqual(model.mutationAction?.reviewID, "review-1")
    XCTAssertEqual(model.mutationAction?.state, .pendingReview)
    XCTAssertEqual(model.mutationAction?.title, "Acción pendiente")
    XCTAssertTrue(model.mutationAction?.showsApproval == true)
    XCTAssertNil(model.draft)
  }

  func testConversationTransportEncodesUUIDAndDecodesDraftFields() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ConversationURLProtocol.self]
    let session = URLSession(configuration: configuration)
    defer { session.invalidateAndCancel() }
    let transport = URLSessionConversationTransport(coreURL: URL(string: "http://localhost:8000")!, session: session)
    let id = UUID()
    let reply = try await transport.respond(instruction: "hola", useReasoning: true, conversationID: id)
    XCTAssertEqual(reply.text, "Borrador")
    XCTAssertEqual(reply.planningStatus, "draft_active")
    XCTAssertEqual(reply.draftID, "draft-1")
    XCTAssertEqual(reply.draftStatus, "active")
    XCTAssertEqual(reply.draftTarget, "prueba.txt")
    XCTAssertEqual(reply.draftContent, "hola")
    XCTAssertEqual(reply.draftDigest, id.uuidString) // Stub echoes the UUID read from actual request JSON.
    XCTAssertNil(reply.reviewID)
  }

  func testConversationResponseStillDecodesWithoutDraftFields() throws {
    let data = Data(#"{"message":"Normal","planning_status":"no_match","reasoning_invoked":false,"proposal_only":true,"execution_performed":false,"review_approved":false,"runtime_started":false}"#.utf8)
    let reply = try JSONDecoder().decode(ConversationResponse.self, from: data)
    XCTAssertEqual(reply.message, "Normal")
    XCTAssertNil(reply.draftID)
    XCTAssertNil(reply.draftStatus)
    XCTAssertNil(reply.draftTarget)
    XCTAssertNil(reply.draftContent)
    XCTAssertNil(reply.draftDigest)
  }

  private func draftReply() -> ConversationReply {
    ConversationReply(text: "Borrador", planningStatus: "draft_active", draftID: "draft-1",
                      draftStatus: "active", draftTarget: "prueba.txt", draftContent: "hola", draftDigest: "digest")
  }

  private func deliver(_ reply: ConversationReply, through controller: ConversationInteractionController,
                       model: ConversationPresentationModel, transport: FakeConversationTransport) async {
    let count = transport.requests.count + 1
    model.inputText = "instrucción"
    controller.submit()
    await transport.waitForRequestCount(count)
    transport.complete(request: 0, with: .success(reply))
    await waitUntil { model.state == .complete }
    XCTAssertEqual(model.state, .complete)
  }

  private func waitUntil(_ condition: @escaping () -> Bool) async {
    for _ in 0..<100 where !condition() { try? await Task.sleep(for: .milliseconds(1)) }
  }
}

@MainActor
private final class FakeConversationTransport: ConversationTransport {
  struct Pending { let continuation: CheckedContinuation<ConversationReply, Error> }
  struct Request: Equatable { let instruction: String; let useReasoning: Bool; let conversationID: UUID }
  var requests: [Request] = []
  var pending: [Pending] = []
  func respond(instruction: String, useReasoning: Bool, conversationID: UUID) async throws -> ConversationReply {
    requests.append(Request(instruction: instruction, useReasoning: useReasoning, conversationID: conversationID))
    return try await withCheckedThrowingContinuation { pending.append(Pending(continuation: $0)) }
  }
  func waitForRequestCount(_ count: Int) async {
    for _ in 0..<100 where requests.count < count { await Task.yield() }
  }
  func completeNext(with value: String) { complete(request: 0, with: .success(ConversationReply(text: value, reviewID: nil))) }
  func completeNext(with error: Error) { complete(request: 0, with: .failure(error)) }
  func complete(request index: Int, with result: Result<ConversationReply, Error>) {
    guard index < pending.count else { return }
    let item = pending.remove(at: index)
    item.continuation.resume(with: result)
  }
  func complete(request index: Int, with value: String) { complete(request: index, with: .success(ConversationReply(text: value, reviewID: nil))) }
}

private enum TestError: Error { case failed }

private final class ConversationURLProtocol: URLProtocol {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() {
    do {
      XCTAssertEqual(request.url?.path, "/api/reasoning/conversation/respond")
      XCTAssertEqual(request.httpMethod, "POST")
      var body = request.httpBody ?? Data()
      if let stream = request.httpBodyStream {
        stream.open()
        defer { stream.close() }
        var buffer = [UInt8](repeating: 0, count: 1024)
        while stream.hasBytesAvailable {
          let count = stream.read(&buffer, maxLength: buffer.count)
          if count <= 0 { break }
          body.append(contentsOf: buffer.prefix(count))
        }
      }
      let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
      XCTAssertEqual(json["instruction"] as? String, "hola")
      XCTAssertEqual(json["use_reasoning"] as? Bool, true)
      let id = try XCTUnwrap(json["conversation_id"] as? String)
      XCTAssertNotNil(UUID(uuidString: id))
      let data = try JSONSerialization.data(withJSONObject: [
        "message": "Borrador", "planning_status": "draft_active", "reasoning_invoked": false,
        "proposal_only": true, "execution_performed": false, "review_approved": false, "runtime_started": false,
        "draft_id": "draft-1", "draft_status": "active", "draft_target": "prueba.txt", "draft_content": "hola", "draft_digest": id,
      ])
      client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: data)
      client?.urlProtocolDidFinishLoading(self)
    } catch { client?.urlProtocol(self, didFailWithError: error) }
  }
  override func stopLoading() {}
}
