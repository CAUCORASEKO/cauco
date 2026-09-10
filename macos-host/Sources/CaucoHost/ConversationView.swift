import Foundation
import SwiftUI
import CaucoHostCore

@MainActor final class ConversationPresentationModel: ObservableObject {
  enum State: String { case idle, thinking, complete, error }
  @Published var state: State = .idle
  @Published var inputText = ""
  @Published var response = ""
  @Published var error = ""
}

struct ConversationResponse: Decodable {
  let message: String
  let planningStatus: String
  let reasoningInvoked: Bool
  let proposalOnly: Bool
  let executionPerformed: Bool
  let reviewApproved: Bool
  let runtimeStarted: Bool
  enum CodingKeys: String, CodingKey {
    case message; case planningStatus = "planning_status"; case reasoningInvoked = "reasoning_invoked"
    case proposalOnly = "proposal_only"; case executionPerformed = "execution_performed"
    case reviewApproved = "review_approved"; case runtimeStarted = "runtime_started"
  }
}

protocol ConversationTransport {
  func respond(instruction: String, useReasoning: Bool) async throws -> String
}

struct URLSessionConversationTransport: ConversationTransport {
  let coreURL: URL
  func respond(instruction: String, useReasoning: Bool) async throws -> String {
    var request = URLRequest(url: coreURL.appendingPathComponent("api/reasoning/conversation/respond"))
    request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = try JSONSerialization.data(withJSONObject: ["instruction": instruction, "use_reasoning": useReasoning])
    let (data, response) = try await URLSession.shared.data(for: request)
    guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
    guard (200..<300).contains(http.statusCode) else {
      struct ErrorBody: Decodable { let detail: String? }
      let detail = (try? JSONDecoder().decode(ErrorBody.self, from: data).detail)
      throw ConversationTransportError.server(status: http.statusCode, detail: detail ?? "Advisory conversation is unavailable; no action was taken.")
    }
    let payload = try JSONDecoder().decode(ConversationResponse.self, from: data)
    guard !payload.message.isEmpty else { throw URLError(.cannotParseResponse) }
    return payload.message
  }
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
  private var requestTask: Task<Void, Never>?
  private var generation = 0

  init(presentation: ConversationPresentationModel, transport: ConversationTransport) {
    self.presentation = presentation; self.transport = transport
  }
  convenience init(coreURL: URL, presentation: ConversationPresentationModel) {
    self.init(presentation: presentation, transport: URLSessionConversationTransport(coreURL: coreURL))
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
    requestTask = Task { [weak self] in
      do {
        let response = try await self?.transport.respond(instruction: value, useReasoning: true)
        guard let self, let response, self.generation == token, !Task.isCancelled else { return }
        self.presentation.inputText = ""; self.presentation.response = response; self.presentation.state = .complete
        completion?(.success(response))
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
        Button(handsFree.state == .disabled ? "Chat de voz" : "Cerrar chat de voz") {
          handsFree.state == .disabled ? handsFree.startVoiceSession() : handsFree.endVoiceSession()
        }.buttonStyle(.borderedProminent)
      }
      ScrollView {
        VStack(alignment: .leading, spacing: 12) {
          if presentation.response.isEmpty && presentation.error.isEmpty { Text("¿En qué puedo ayudarte?").foregroundStyle(.secondary).frame(maxWidth: .infinity, minHeight: 280, alignment: .center) }
          if !presentation.response.isEmpty { message("Cauco", presentation.response) }
          if !presentation.error.isEmpty { Text(presentation.error).foregroundStyle(.red) }
        }.frame(maxWidth: .infinity, alignment: .leading)
      }
      TextEditor(text: $presentation.inputText).frame(minHeight: 100).overlay(RoundedRectangle(cornerRadius: 10).stroke(.quaternary))
      HStack { Text("Advisory planning only.").font(.caption).foregroundStyle(.secondary); Spacer(); Button(presentation.state == .thinking ? "Pensando…" : "Enviar", action: controller.submit).keyboardShortcut(.return, modifiers: [.command]).disabled(presentation.state == .thinking) }
    }.padding(20).frame(minWidth: 580, minHeight: 620)
  }
  private func statusColor(_ tone: VoiceActivationStatusTone) -> Color { tone == .error ? .red : tone == .active ? .green : .secondary }
  private func message(_ label: String, _ text: String) -> some View {
    VStack(alignment: .leading, spacing: 5) { Text(label).font(.caption.bold()); Text(text).textSelection(.enabled) }.padding(12).background(.quaternary.opacity(0.35)).clipShape(RoundedRectangle(cornerRadius: 10))
  }
}
