import Foundation
import SwiftUI

@MainActor final class ConversationModel: ObservableObject {
  enum State: String { case idle, thinking, complete, error }
  @Published var state: State = .idle
  @Published var instruction = ""
  @Published var response = ""
  @Published var error = ""
  private let coreURL: URL

  init(coreURL: URL) { self.coreURL = coreURL }

  func submit() {
    let value = instruction.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !value.isEmpty, state != .thinking else { return }
    state = .thinking; response = ""; error = ""
    Task { await request(value) }
  }

  private func request(_ instruction: String) async {
    var request = URLRequest(url: coreURL.appendingPathComponent("api/reasoning/conversation/respond"))
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = try? JSONSerialization.data(withJSONObject: ["instruction": instruction, "use_reasoning": true])
    do {
      let (data, response) = try await URLSession.shared.data(for: request)
      guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else { throw URLError(.badServerResponse) }
      let payload = try JSONDecoder().decode(ConversationResponse.self, from: data)
      guard !payload.message.isEmpty else {
        throw URLError(.cannotParseResponse)
      }
      responseText(payload.message)
    } catch { failure("Advisory planning is unavailable. No action was taken.") }
  }

  private func responseText(_ value: String) {
    response = value; instruction = ""; state = .complete
  }
  private func failure(_ value: String) { error = value; state = .error }
}

private struct ConversationResponse: Decodable {
  let message: String
  let planningStatus: String
  let reasoningInvoked: Bool
  let proposalOnly: Bool
  let executionPerformed: Bool
  let reviewApproved: Bool
  let runtimeStarted: Bool

  enum CodingKeys: String, CodingKey {
    case message
    case planningStatus = "planning_status"
    case reasoningInvoked = "reasoning_invoked"
    case proposalOnly = "proposal_only"
    case executionPerformed = "execution_performed"
    case reviewApproved = "review_approved"
    case runtimeStarted = "runtime_started"
  }
}

struct ConversationView: View {
  @StateObject private var model: ConversationModel
  init(coreURL: URL) { _model = StateObject(wrappedValue: ConversationModel(coreURL: coreURL)) }

  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      Label("Cauco Conversation", systemImage: "bubble.left.and.bubble.right.fill").font(.title2.bold())
      Text("Advisory planning only. Cauco will not execute or mutate anything from this window.").font(.callout).foregroundStyle(.secondary)
      Text("State: \(model.state.rawValue.capitalized)").font(.headline)
      if !model.response.isEmpty { message("Cauco", model.response) }
      if !model.error.isEmpty { Text(model.error).foregroundStyle(.red) }
      TextEditor(text: $model.instruction).frame(minHeight: 130).overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
      HStack { Spacer(); Button(model.state == .thinking ? "Planning…" : "Plan", action: model.submit).keyboardShortcut(.return, modifiers: [.command]).disabled(model.state == .thinking) }
      Spacer()
    }.padding(24).frame(minWidth: 420, minHeight: 500)
  }

  private func message(_ label: String, _ text: String) -> some View {
    VStack(alignment: .leading, spacing: 5) { Text(label).font(.caption.bold()); Text(text).textSelection(.enabled) }.padding(12).background(.quaternary.opacity(0.35)).clipShape(RoundedRectangle(cornerRadius: 10))
  }
}
