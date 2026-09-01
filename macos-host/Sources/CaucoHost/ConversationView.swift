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
    guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else { throw URLError(.badServerResponse) }
    let payload = try JSONDecoder().decode(ConversationResponse.self, from: data)
    guard !payload.message.isEmpty else { throw URLError(.cannotParseResponse) }
    return payload.message
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
  private let controller: ConversationInteractionController
  init(presentation: ConversationPresentationModel, controller: ConversationInteractionController) {
    self.presentation = presentation; self.controller = controller
  }
  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      Label("Cauco Conversation", systemImage: "bubble.left.and.bubble.right.fill").font(.title2.bold())
      Text("Advisory planning only. Cauco will not execute or mutate anything from this window.").font(.callout).foregroundStyle(.secondary)
      Text("State: \(presentation.state.rawValue.capitalized)").font(.headline)
      if !presentation.response.isEmpty { message("Cauco", presentation.response) }
      if !presentation.error.isEmpty { Text(presentation.error).foregroundStyle(.red) }
      TextEditor(text: $presentation.inputText).frame(minHeight: 130).overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
      HStack { Spacer(); Button(presentation.state == .thinking ? "Planning…" : "Plan", action: controller.submit).keyboardShortcut(.return, modifiers: [.command]).disabled(presentation.state == .thinking) }
      Spacer()
    }.padding(24).frame(minWidth: 420, minHeight: 500)
  }
  private func message(_ label: String, _ text: String) -> some View {
    VStack(alignment: .leading, spacing: 5) { Text(label).font(.caption.bold()); Text(text).textSelection(.enabled) }.padding(12).background(.quaternary.opacity(0.35)).clipShape(RoundedRectangle(cornerRadius: 10))
  }
}
