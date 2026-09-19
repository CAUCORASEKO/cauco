import AVFoundation
import CaucoHostCore
import Foundation

enum QwenTTSError: LocalizedError {
  case invalidResponse
  case server(Int)
  case audioPlayback(Error)

  var errorDescription: String? {
    switch self {
    case .invalidResponse:
      return "Qwen TTS returned no playable audio."
    case .server(let status):
      return "Qwen TTS request failed (HTTP \(status))."
    case .audioPlayback(let error):
      return error.localizedDescription
    }
  }
}

@MainActor
final class QwenSpeechSynthesizer: NSObject, SpeechSynthesizer {
  private static let endpoint =
    URL(string: "http://127.0.0.1:7860/v1/tts/clone")!

  private let fallback: SpeechSynthesizer
  private let session: URLSession

  private let engine = AVAudioEngine()
  private let player = AVAudioPlayerNode()

  private var generation = 0
  private var requestTask: Task<Void, Never>?
  private var completion: (() -> Void)?

  private(set) var state: SpeechSynthesisState = .idle

  convenience override init() {
    let configuration = URLSessionConfiguration.default
    configuration.timeoutIntervalForRequest = 180
    configuration.timeoutIntervalForResource = 180

    self.init(
      fallback: AppleSpeechSynthesizer(),
      session: URLSession(configuration: configuration)
    )
  }

  init(
    fallback: SpeechSynthesizer,
    session: URLSession = .shared
  ) {
    self.fallback = fallback
    self.session = session

    super.init()

    engine.attach(player)
  }

  func speak(
    _ text: String,
    locale: Locale,
    onComplete: @escaping () -> Void,
    onError: @escaping (Error) -> Void
  ) {
    guard !text.isEmpty,
          requestTask == nil,
          !player.isPlaying else {
      onError(VoiceFoundationError.busy)
      return
    }

    generation += 1
    let token = generation

    state = .speaking
    completion = onComplete

    requestTask = Task { [weak self] in
      guard let self else { return }

      do {
        let wav = try await self.synthesize(text: text)

        guard !Task.isCancelled,
              self.generation == token else {
          return
        }

        try self.play(wav: wav, token: token)
      } catch is CancellationError {
      } catch {
        guard self.generation == token else { return }

        print("QWEN_TTS_ERROR:", error)
        print("QWEN_TTS_ERROR_DESCRIPTION:", error.localizedDescription)

        self.requestTask = nil

        self.fallback.speak(
          text,
          locale: locale,
          onComplete: { [weak self] in
            guard let self,
                  self.generation == token else {
              return
            }

            self.state = .completed
            self.completion?()
            self.completion = nil
          },
          onError: { [weak self] fallbackError in
            guard let self,
                  self.generation == token else {
              return
            }

            self.state = .failed
            self.completion = nil
            onError(fallbackError)
          }
        )
      }
    }
  }

  func stop() {
    generation += 1

    requestTask?.cancel()
    requestTask = nil

    player.stop()
    engine.stop()

    fallback.stop()

    completion = nil
    state = .stopped
  }

  private func synthesize(text: String) async throws -> Data {
    let body: [String: Any] = [
      "text": text,
      "voice": "Cauco",
      "temperature": 1.0,
      "model": "1.7B-Base"
    ]

    let data = try JSONSerialization.data(withJSONObject: body)

    var request = URLRequest(url: Self.endpoint)
    request.httpMethod = "POST"
    request.httpBody = data
    request.setValue(
      "application/json",
      forHTTPHeaderField: "Content-Type"
    )

    let (responseData, response) = try await session.data(for: request)

    guard let http = response as? HTTPURLResponse else {
      throw QwenTTSError.invalidResponse
    }

    guard (200..<300).contains(http.statusCode) else {
      throw QwenTTSError.server(http.statusCode)
    }

    guard !responseData.isEmpty else {
      throw QwenTTSError.invalidResponse
    }

    return responseData
  }

  private func play(wav: Data, token: Int) throws {
    let temporaryURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("cauco-qwen-\(UUID().uuidString).wav")

    try wav.write(to: temporaryURL)

    do {
      let file = try AVAudioFile(forReading: temporaryURL)

      engine.connect(
        player,
        to: engine.mainMixerNode,
        format: file.processingFormat
      )

      engine.prepare()

      do {
        try engine.start()
      } catch {
        try? FileManager.default.removeItem(at: temporaryURL)
        throw QwenTTSError.audioPlayback(error)
      }

      requestTask = nil

      player.scheduleFile(
        file,
        at: nil,
        completionCallbackType: .dataPlayedBack
      ) { [weak self] _ in
        Task { @MainActor [weak self] in
          try? FileManager.default.removeItem(at: temporaryURL)

          guard let self,
                self.generation == token else {
            return
          }

          self.player.stop()
          self.engine.stop()

          self.state = .completed
          self.completion?()
          self.completion = nil
        }
      }

      player.play()
    } catch {
      try? FileManager.default.removeItem(at: temporaryURL)
      throw QwenTTSError.audioPlayback(error)
    }
  }
}
