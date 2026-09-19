import AVFoundation
import Foundation
import CaucoHostCore

struct GeminiTTSConfiguration: Equatable {
  static let model = "gemini-3.1-flash-tts-preview"
  static let voice = "Charon"
  let apiKey: String

  static func environment(_ environment: [String: String] = ProcessInfo.processInfo.environment) -> GeminiTTSConfiguration? {
    guard let key = environment["GEMINI_API_KEY"]?.trimmingCharacters(in: .whitespacesAndNewlines), !key.isEmpty else { return nil }
    return GeminiTTSConfiguration(apiKey: key)
  }
}

enum GeminiTTSError: LocalizedError {
  case invalidResponse, server(Int), audioPlayback(Error)
  var errorDescription: String? {
    switch self { case .invalidResponse: return "Gemini TTS returned no playable audio."; case .server(let status): return "Gemini TTS request failed (HTTP \(status))."; case .audioPlayback(let error): return error.localizedDescription }
  }
}

@MainActor final class GeminiSpeechSynthesizer: NSObject, SpeechSynthesizer {
  private let configuration: GeminiTTSConfiguration
  private let fallback: SpeechSynthesizer
  private let session: URLSession
  private let engine = AVAudioEngine()
  private let player = AVAudioPlayerNode()
  private var generation = 0
  private var requestTask: Task<Void, Never>?
  private var completion: (() -> Void)?
  private(set) var state: SpeechSynthesisState = .idle

  convenience init(configuration: GeminiTTSConfiguration) {
    self.init(configuration: configuration, fallback: AppleSpeechSynthesizer(), session: .shared)
  }

  init(configuration: GeminiTTSConfiguration, fallback: SpeechSynthesizer, session: URLSession = .shared) {
    self.configuration = configuration; self.fallback = fallback; self.session = session
    super.init()
    engine.attach(player)
  }

  func speak(_ text: String, locale: Locale, onComplete: @escaping () -> Void, onError: @escaping (Error) -> Void) {
    guard !text.isEmpty, requestTask == nil, !player.isPlaying else { onError(VoiceFoundationError.busy); return }
    generation += 1
    let token = generation
    state = .speaking
    completion = onComplete
    requestTask = Task { [weak self] in
      guard let self else { return }
      do {
        let pcm = try await self.synthesize(text: text, locale: locale)
        guard !Task.isCancelled, self.generation == token else { return }
        try self.play(pcm: pcm, token: token)
      } catch is CancellationError {
      } catch {
        guard self.generation == token else { return }
        self.requestTask = nil
        self.fallback.speak(text, locale: locale, onComplete: { [weak self] in
          guard let self, self.generation == token else { return }
          self.state = .completed; self.completion?(); self.completion = nil
        }, onError: { [weak self] fallbackError in
          guard let self, self.generation == token else { return }
          self.state = .failed; self.completion = nil; onError(fallbackError)
        })
      }
    }
  }

  func stop() {
    generation += 1
    requestTask?.cancel(); requestTask = nil
    player.stop(); engine.stop(); fallback.stop()
    completion = nil; state = .stopped
  }

  private func synthesize(text: String, locale: Locale) async throws -> Data {
    let prompt = "Synthesize the following Spanish text exactly. Voice direction: adult male personal AI assistant, calm, intelligent, confident, natural, medium-low register, conversational Spanish, moderate pace, smooth transitions, no exaggerated pauses, no radio-announcer cadence, no theatrical delivery. Spoken transcript:\n\(text)"
    let body: [String: Any] = [
      "model": GeminiTTSConfiguration.model,
      "input": prompt,
      "response_format": ["type": "audio"],
      "generation_config": ["speech_config": [["voice": GeminiTTSConfiguration.voice, "language": locale.identifier]]]
    ]
    let data = try JSONSerialization.data(withJSONObject: body)
    for attempt in 0...1 {
      var request = URLRequest(url: URL(string: "https://generativelanguage.googleapis.com/v1beta/interactions")!)
      request.httpMethod = "POST"; request.httpBody = data
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
      request.setValue(configuration.apiKey, forHTTPHeaderField: "x-goog-api-key")
      request.setValue("2026-05-20", forHTTPHeaderField: "Api-Revision")
      let (responseData, response) = try await session.data(for: request)
      guard let http = response as? HTTPURLResponse else { throw GeminiTTSError.invalidResponse }
      if http.statusCode == 500, attempt == 0 { continue }
      guard (200..<300).contains(http.statusCode) else { throw GeminiTTSError.server(http.statusCode) }
      guard let object = try JSONSerialization.jsonObject(with: responseData) as? [String: Any],
            let outputAudio = object["output_audio"] as? [String: Any],
            let encoded = outputAudio["data"] as? String,
            let pcm = Data(base64Encoded: encoded), !pcm.isEmpty else { throw GeminiTTSError.invalidResponse }
      return pcm
    }
    throw GeminiTTSError.invalidResponse
  }

  private func play(pcm: Data, token: Int) throws {
    guard pcm.count.isMultiple(of: 2) else { throw GeminiTTSError.invalidResponse }
    let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 24_000, channels: 1, interleaved: true)!
    let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(pcm.count / 2))!
    buffer.frameLength = buffer.frameCapacity
    _ = pcm.withUnsafeBytes { source in memcpy(buffer.int16ChannelData![0], source.baseAddress!, pcm.count) }
    engine.connect(player, to: engine.mainMixerNode, format: format)
    engine.prepare()
    do { try engine.start() } catch { throw GeminiTTSError.audioPlayback(error) }
    requestTask = nil
    player.scheduleBuffer(buffer) { [weak self] in
      Task { @MainActor [weak self] in
        guard let self, self.generation == token else { return }
        self.player.stop(); self.engine.stop(); self.state = .completed; self.completion?(); self.completion = nil
      }
    }
    player.play()
  }
}
