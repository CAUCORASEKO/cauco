import Foundation
import SwiftUI
import CaucoHostCore

@MainActor final class ConversationPresentationModel: ObservableObject {
  enum State: String { case idle, thinking, complete, error }
  let conversationID = UUID()
  @Published var draft: ConversationDraft?
  var activeDraft: ConversationDraft? { draft?.status == "active" ? draft : nil }
  @Published var state: State = .idle
  @Published var inputText = ""
  @Published var response = ""
  @Published var error = ""
  @Published var mutationAction: MutationAction? = nil
}

enum MutationActionState { case pendingReview, approving, previewing, awaitingConfirmation, confirming, completed, cancelled, error }
struct MutationAction {
  var title: String { "Acción pendiente" }
  var showsApproval: Bool { state == .pendingReview }
  var state: MutationActionState; let reviewID: String; var executionID: String?; var stepIndex: Int?; var preview: MutationPreviewDTO?; var message: String = ""
}
struct ConversationReply {
  let text: String
  var reviewID: String? = nil
  var planningStatus: String? = nil
  var draftID: String? = nil
  var draftStatus: String? = nil
  var draftTarget: String? = nil
  var draftContent: String? = nil
  var draftDigest: String? = nil
}

struct ConversationDraft {
  let id: String
  let status: String
  let target: String
  let content: String
  let digest: String?
  let planningStatus: String?
  var title: String { status == "finalized" ? "Archivo finalizado" : "Resultado / Revisión" }
  var statusText: String {
    if planningStatus == "draft_conflict" { return "Conflicto: el destino apareció o cambió durante la revisión. No se sobrescribió." }
    if planningStatus == "draft_verification_failed" { return "No se pudo verificar la finalización. El borrador sigue activo." }
    return status == "active" ? "Borrador activo · Archivo final aún no guardado" : status == "finalized" ? "Guardado y verificado" : "Borrador cerrado"
  }
  var prompt: String? { status == "active" && planningStatus != "draft_conflict" && planningStatus != "draft_verification_failed" ? "¿Está bien o quieres hacer cambios?" : nil }
}

struct ReviewDTO: Decodable { let reviewID: String; let status: String; let plan: PlanDTO; let executionAuthorized: Bool; let executionPerformed: Bool
  enum CodingKeys: String, CodingKey { case reviewID = "review_id", status, plan; case executionAuthorized = "execution_authorized"; case executionPerformed = "execution_performed" }
}
struct PlanDTO: Decodable { let steps: [PlanStepDTO] }
struct PlanStepDTO: Decodable { let order: Int; let toolReference: ToolReferenceDTO
  enum CodingKeys: String, CodingKey { case order; case toolReference = "tool_reference" }
}
struct ToolReferenceDTO: Decodable { let toolID: String; let operationID: String; let target: String?
  enum CodingKeys: String, CodingKey { case toolID = "tool_id", operationID = "operation_id", target }
}
struct ExecutionDTO: Decodable { let executionID: String; let stepRecords: [ExecutionStepDTO]
  enum CodingKeys: String, CodingKey { case executionID = "execution_id"; case stepRecords = "step_records" }
}
struct ExecutionStepDTO: Decodable { let stepIndex: Int; let toolID: String; let operationID: String; let target: String?
  enum CodingKeys: String, CodingKey { case stepIndex = "step_index", toolID = "tool_id", operationID = "operation_id", target }
}
struct MutationPreviewDTO: Decodable { let previewID: String; let previewDigest: String; let confirmationPhrase: String; let target: String; let beforeState: [String: JSONValue]?; let proposedAfterState: [String: JSONValue]?; let diffPreview: String?; let status: String
  enum CodingKeys: String, CodingKey { case previewID = "preview_id", previewDigest = "preview_digest", confirmationPhrase = "confirmation_phrase", target, beforeState = "before_state", proposedAfterState = "proposed_after_state", diffPreview = "diff_preview", status }
}
enum JSONValue: Decodable { case string(String), bool(Bool), number(Double), object([String: JSONValue]), array([JSONValue]), null
  init(from d: Decoder) throws { let c = try d.singleValueContainer(); if c.decodeNil() { self = .null } else if let v = try? c.decode(String.self) { self = .string(v) } else if let v = try? c.decode(Bool.self) { self = .bool(v) } else if let v = try? c.decode(Double.self) { self = .number(v) } else if let v = try? c.decode([String: JSONValue].self) { self = .object(v) } else { self = .array(try c.decode([JSONValue].self)) } }
}

struct ConversationResponse: Decodable {
  let message: String
  let planningStatus: String
  let reasoningInvoked: Bool
  let proposalOnly: Bool
  let executionPerformed: Bool
  let reviewApproved: Bool
  let runtimeStarted: Bool
  let reviewID: String?
  let draftID: String?
  let draftStatus: String?
  let draftTarget: String?
  let draftContent: String?
  let draftDigest: String?
  enum CodingKeys: String, CodingKey {
    case draftID = "draft_id", draftStatus = "draft_status", draftTarget = "draft_target", draftContent = "draft_content", draftDigest = "draft_digest"
    case message; case planningStatus = "planning_status"; case reasoningInvoked = "reasoning_invoked"
    case proposalOnly = "proposal_only"; case executionPerformed = "execution_performed"
    case reviewApproved = "review_approved"; case runtimeStarted = "runtime_started"; case reviewID = "review_id"
  }
}

protocol ConversationTransport {
  func respond(instruction: String, useReasoning: Bool, conversationID: UUID) async throws -> ConversationReply
}

protocol MutationTransport { func review(_ id: String) async throws -> ReviewDTO; func approve(_ id: String) async throws -> ReviewDTO; func execution(_ reviewID: String) async throws -> ExecutionDTO; func preview(_ executionID: String, _ step: Int) async throws -> MutationPreviewDTO; func confirm(_ executionID: String, _ step: Int, _ preview: MutationPreviewDTO) async throws; func cancel(_ executionID: String, _ step: Int) async throws }

struct URLSessionConversationTransport: ConversationTransport {
  let coreURL: URL
  var session: URLSession = .shared
  func respond(instruction: String, useReasoning: Bool, conversationID: UUID) async throws -> ConversationReply {
    var request = URLRequest(url: coreURL.appendingPathComponent("api/reasoning/conversation/respond"))
    request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = try JSONSerialization.data(withJSONObject: ["instruction": instruction, "use_reasoning": useReasoning, "conversation_id": conversationID.uuidString])
    let (data, response) = try await session.data(for: request)
    guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
    guard (200..<300).contains(http.statusCode) else {
      struct ErrorBody: Decodable { let detail: String? }
      let detail = (try? JSONDecoder().decode(ErrorBody.self, from: data).detail)
      throw ConversationTransportError.server(status: http.statusCode, detail: detail ?? "Advisory conversation is unavailable; no action was taken.")
    }
    let payload = try JSONDecoder().decode(ConversationResponse.self, from: data)
    guard !payload.message.isEmpty else { throw URLError(.cannotParseResponse) }
    return ConversationReply(
      text: payload.message, reviewID: payload.reviewID, planningStatus: payload.planningStatus,
      draftID: payload.draftID, draftStatus: payload.draftStatus, draftTarget: payload.draftTarget,
      draftContent: payload.draftContent, draftDigest: payload.draftDigest
    )
  }
}

extension URLSessionConversationTransport: MutationTransport {
  private func call<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil, as type: T.Type) async throws -> T { var r = URLRequest(url: coreURL.appendingPathComponent(path)); r.httpMethod = method; r.setValue("application/json", forHTTPHeaderField: "Content-Type"); if let body { r.httpBody = try JSONSerialization.data(withJSONObject: body) }; let (d, response) = try await URLSession.shared.data(for: r); guard let h = response as? HTTPURLResponse, (200..<300).contains(h.statusCode) else { throw ConversationTransportError.server(status: (response as? HTTPURLResponse)?.statusCode ?? 0, detail: "The pending action could not be completed.") }; return try JSONDecoder().decode(T.self, from: d) }
  func review(_ id: String) async throws -> ReviewDTO { try await call("api/agents/plan-reviews/\(id)", as: ReviewDTO.self) }
  func approve(_ id: String) async throws -> ReviewDTO { try await call("api/agents/plan-reviews/\(id)/approve", method: "POST", body: [:], as: ReviewDTO.self) }
  func execution(_ id: String) async throws -> ExecutionDTO { try await call("api/executions", method: "POST", body: ["review_id": id], as: ExecutionDTO.self) }
  func preview(_ id: String, _ step: Int) async throws -> MutationPreviewDTO { try await call("api/executions/\(id)/steps/\(step)/mutation-preview", method: "POST", body: [:], as: MutationPreviewDTO.self) }
  func confirm(_ id: String, _ step: Int, _ p: MutationPreviewDTO) async throws { let _: ExecutionDTO = try await call("api/executions/\(id)/steps/\(step)/confirm-mutation", method: "POST", body: ["preview_id": p.previewID, "preview_digest": p.previewDigest, "confirmation_phrase": p.confirmationPhrase], as: ExecutionDTO.self) }
  func cancel(_ id: String, _ step: Int) async throws { let _: MutationPreviewDTO = try await call("api/executions/\(id)/steps/\(step)/cancel-mutation-preview", method: "POST", body: [:], as: MutationPreviewDTO.self) }
}

enum ConversationTransportError: LocalizedError {
  case server(status: Int, detail: String)
  var errorDescription: String? {
    if case let .server(_, detail) = self { return detail }
    return nil
  }
}

@MainActor final class ConversationInteractionController: ConversationResponding {
  let presentation: ConversationPresentationModel
  private let transport: ConversationTransport
  private let mutationTransport: MutationTransport?
  private var requestTask: Task<Void, Never>?
  private var generation = 0

  init(presentation: ConversationPresentationModel, transport: ConversationTransport, mutationTransport: MutationTransport? = nil) {
    self.presentation = presentation; self.transport = transport; self.mutationTransport = mutationTransport
  }
  convenience init(coreURL: URL, presentation: ConversationPresentationModel) {
    let transport = URLSessionConversationTransport(coreURL: coreURL); self.init(presentation: presentation, transport: transport, mutationTransport: transport)
  }
  func submit() { submit(instruction: presentation.inputText, completion: nil) }

  func respond(instruction: String, useReasoning: Bool, completion: @escaping (Result<String, Error>) -> Void) {
    guard useReasoning else { completion(.failure(URLError(.badURL))); return }
    submit(instruction: instruction, completion: completion)
  }

  private func submit(instruction: String, completion: ((Result<String, Error>) -> Void)?) {
    let value = instruction.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !value.isEmpty, presentation.state != .thinking else { return }
    requestTask?.cancel(); generation += 1; let token = generation
    presentation.state = .thinking; presentation.response = ""; presentation.error = ""
    let conversationID = presentation.conversationID
    requestTask = Task { [weak self] in
      do {
        let response = try await self?.transport.respond(instruction: value, useReasoning: true, conversationID: conversationID)
        guard let self, let response, self.generation == token, !Task.isCancelled else { return }
        self.presentation.inputText = ""; self.presentation.response = response.text; self.presentation.state = .complete
        if let id = response.draftID, let status = response.draftStatus,
           let target = response.draftTarget, let content = response.draftContent {
          self.presentation.draft = ConversationDraft(
            id: id, status: status, target: target, content: content,
            digest: response.draftDigest, planningStatus: response.planningStatus
          )
          self.presentation.mutationAction = nil
        } else if let reviewID = response.reviewID {
          self.presentation.draft = nil
          self.presentation.mutationAction = MutationAction(state: .pendingReview, reviewID: reviewID)
        }
        completion?(.success(response.text))
      } catch {
        guard let self, self.generation == token, !Task.isCancelled else { return }
        self.presentation.error = "Advisory planning is unavailable. No action was taken."; self.presentation.state = .error
        completion?(.failure(error))
      }
    }
  }
  func cancel() {
    generation += 1; requestTask?.cancel(); requestTask = nil
    if presentation.state == .thinking { presentation.state = .idle }
  }
  func approveMutation() { guard let transport = mutationTransport, var action = presentation.mutationAction, action.state == .pendingReview else { return }; action.state = .approving; presentation.mutationAction = action; Task { do { _ = try await transport.review(action.reviewID); _ = try await transport.approve(action.reviewID); action.state = .previewing; presentation.mutationAction = action; let execution = try await transport.execution(action.reviewID); guard let step = execution.stepRecords.first(where: { $0.toolID == "filesystem" && $0.operationID == "write_text_file" }) else { throw ConversationTransportError.server(status: 409, detail: "No filesystem mutation step is available.") }; action.executionID = execution.executionID; action.stepIndex = step.stepIndex; let preview = try await transport.preview(execution.executionID, step.stepIndex); action.preview = preview; action.state = .awaitingConfirmation; presentation.mutationAction = action } catch { action.state = .error; action.message = "The pending action failed; no write was assumed."; presentation.mutationAction = action } } }
  func confirmMutation() { guard let transport = mutationTransport, var action = presentation.mutationAction, action.state == .awaitingConfirmation, let id = action.executionID, let step = action.stepIndex, let preview = action.preview else { return }; action.state = .confirming; presentation.mutationAction = action; Task { do { try await transport.confirm(id, step, preview); action.state = .completed; action.message = "Workspace file written."; presentation.mutationAction = action } catch { action.state = .error; action.message = "Confirmation failed; no write was assumed."; presentation.mutationAction = action } } }
  func cancelMutation() { guard let transport = mutationTransport, var action = presentation.mutationAction, let id = action.executionID, let step = action.stepIndex, action.state == .awaitingConfirmation else { presentation.mutationAction = nil; return }; action.state = .confirming; presentation.mutationAction = action; Task { do { try await transport.cancel(id, step); action.state = .cancelled; presentation.mutationAction = action } catch { action.state = .error; action.message = "Cancellation could not be confirmed."; presentation.mutationAction = action } } }
}

struct ConversationView: View {
  @ObservedObject private var presentation: ConversationPresentationModel
  @ObservedObject private var handsFree: HostHandsFreeService
  private let controller: ConversationInteractionController
  private let showSettings: () -> Void
  init(presentation: ConversationPresentationModel, controller: ConversationInteractionController, handsFree: HostHandsFreeService?, showSettings: @escaping () -> Void) {
    self.presentation = presentation; self.controller = controller
    precondition(handsFree != nil, "The main conversation requires the configured hands-free service.")
    self.handsFree = handsFree!
    self.showSettings = showSettings
  }
  var body: some View {
    VStack(spacing: 14) {
      HStack {
        Label("Cauco", systemImage: "bubble.left.and.bubble.right.fill").font(.title2.bold())
        Spacer()
        Picker("Idioma", selection: Binding(get: { handsFree.speechLanguage }, set: { handsFree.setSpeechLanguage($0) })) {
          ForEach(HostSpeechLanguage.allCases) { Text($0.title).tag($0) }
        }.labelsHidden().frame(width: 120)
        Button(action: showSettings) { Image(systemName: "gearshape") }.accessibilityLabel("Settings")
      }
      HStack {
        let status = VoiceActivationRuntimeStatus.forState(handsFree.state)
        Label(status.title, systemImage: status.symbolName).foregroundStyle(statusColor(status.tone))
        Text(status.detail).font(.caption).foregroundStyle(.secondary)
        Spacer()
        Button(handsFree.voiceSessionButtonTitle) {
          handsFree.isVoiceSessionActive ? handsFree.endVoiceSession() : handsFree.startVoiceSession()
        }.buttonStyle(.borderedProminent)
      }
      ScrollView {
        VStack(alignment: .leading, spacing: 12) {
          if presentation.response.isEmpty && presentation.error.isEmpty { Text("¿En qué puedo ayudarte?").foregroundStyle(.secondary).frame(maxWidth: .infinity, minHeight: 280, alignment: .center) }
          if !presentation.response.isEmpty { message("Cauco", presentation.response) }
          if let draft = presentation.draft { draftCard(draft) }
          if let action = presentation.mutationAction { mutationCard(action) }
          if !presentation.error.isEmpty { Text(presentation.error).foregroundStyle(.red) }
        }.frame(maxWidth: .infinity, alignment: .leading)
      }
      TextEditor(text: $presentation.inputText).frame(minHeight: 100).overlay(RoundedRectangle(cornerRadius: 10).stroke(.quaternary))
      HStack { Text("Puedes revisar y ajustar el resultado en el chat.").font(.caption).foregroundStyle(.secondary); Spacer(); Button(presentation.state == .thinking ? "Pensando…" : "Enviar", action: controller.submit).keyboardShortcut(.return, modifiers: [.command]).disabled(presentation.state == .thinking) }
    }.padding(20).frame(minWidth: 580, minHeight: 620)
  }
  private func statusColor(_ tone: VoiceActivationStatusTone) -> Color { tone == .error ? .red : tone == .active ? .green : .secondary }
  private func message(_ label: String, _ text: String) -> some View {
    VStack(alignment: .leading, spacing: 5) { Text(label).font(.caption.bold()); Text(text).textSelection(.enabled) }.padding(12).background(.quaternary.opacity(0.35)).clipShape(RoundedRectangle(cornerRadius: 10))
  }
  private func draftCard(_ draft: ConversationDraft) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(draft.title).font(.headline)
      Text(draft.target).font(.caption).textSelection(.enabled)
      Text(String(draft.content.prefix(20_000))).font(.body.monospaced()).textSelection(.enabled)
      if draft.content.count > 20_000 { Text("Vista previa truncada").font(.caption) }
      Text(draft.statusText).foregroundStyle(draft.planningStatus == "draft_conflict" ? .orange : .secondary)
      if let prompt = draft.prompt { Text(prompt) }
    }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
      .background(.blue.opacity(0.08)).clipShape(RoundedRectangle(cornerRadius: 10))
  }
  private func mutationCard(_ action: MutationAction) -> some View {
    VStack(alignment: .leading, spacing: 8) { Text(action.title).font(.headline); Text(action.preview?.target ?? "Escritura de archivo del workspace").font(.caption); if let preview = action.preview { Text(preview.diffPreview ?? "Vista previa disponible").textSelection(.enabled) }; if action.showsApproval { Button("Aprobar", action: controller.approveMutation) } else if action.state == .awaitingConfirmation { HStack { Button("Confirmar escritura", action: controller.confirmMutation).buttonStyle(.borderedProminent); Button("Cancelar", action: controller.cancelMutation) } } else { Text(action.message.isEmpty ? String(describing: action.state) : action.message).foregroundStyle(action.state == .error ? .red : .secondary) } }.padding(12).background(.blue.opacity(0.08)).clipShape(RoundedRectangle(cornerRadius: 10))
  }
}
