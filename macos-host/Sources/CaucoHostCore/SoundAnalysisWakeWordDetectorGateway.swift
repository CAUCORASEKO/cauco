import AVFoundation
import CoreML
import Foundation
import OSLog

public struct WakeWordPilotConfiguration: Sendable {
  public static let `default` = WakeWordPilotConfiguration()
  public let phraseKey = "hola_cauco"
  public let modelLabel = "hola_cauco"
  public let confidenceThreshold = 0.85
  public let consecutiveWindows = 3
  public let inferenceHopSamples = 2_560
  public let inferenceWindowSamples = 16_000
}

public final class WakeWordModelProvider: @unchecked Sendable {
  private let modelURL: URL?
  public init(modelURL: URL? = Bundle.main.url(forResource: "HolaCauco", withExtension: "mlmodelc", subdirectory: "WakeWord")) { self.modelURL = modelURL }
  public var available: Bool { modelURL != nil }
  public func load() throws -> MLModel { guard let modelURL else { throw BrokerError.capabilityUnavailable }; return try MLModel(contentsOf: modelURL, configuration: MLModelConfiguration()) }
}

/// Local feature-input Core ML pilot. SoundAnalysis is intentionally not used.
public final class SoundAnalysisWakeWordDetectorGateway: WakeWordDetectorGateway, @unchecked Sendable {
  private static let logger = Logger(subsystem: "com.cauco.host", category: "wake-runtime-metrics")
  private struct Metrics {
    var intervalStart = Date()
    var audioCallbacks = 0
    var convertedBuffers = 0
    var inferenceAttempts = 0
    var successfulInferences = 0
    var inferenceDuration = 0.0
    var maximumInferenceDuration = 0.0
    var featureDuration = 0.0
    var pendingWork = 0
    var maximumBacklog = 0
    var skippedWindows = 0
    var droppedWork = 0
    var engineStarts = 0
    var engineStops = 0
    var computeTime = 0.0
    var inferenceSequence = 0
  }
  private let provider: WakeWordModelProvider; private let pilot: WakeWordPilotConfiguration; private let lock = NSLock(); private let queue = DispatchQueue(label: "cauco.wake.coreml-analysis")
  private let extractor = TemporalWakeFeatureExtractor()
  private var engine: AVAudioEngine?; private var handler: (@Sendable (WakeWordDetectionSignal) -> Void)?; private var buffer = BoundedMonoAudioBuffer(); private var predictor: TemporalWakeModelPredictor?; private var positiveWindows = 0; private var pendingSamples = 0; private var generation = 0; private var active = false; private var metrics = Metrics(); private var metricsTimer: DispatchSourceTimer?; private var pendingAudio: (AVAudioPCMBuffer, AVAudioConverter, AVAudioFormat, Int)?; private var workerScheduled = false; private var previousFeatures: [Double]?
  private var triggerDiagnostics: [RuntimeTriggerDiagnostic] = []
  private struct RuntimeTriggerDiagnostic: Codable {
    let inferenceSequence: Int; let relativeTimestamp: Double; let features: [Double]
    let coreMLProbability: Double; let coreMLLogit: Double
    let rms: Double; let peakAbsoluteAmplitude: Double; let meanDC: Double; let zeroCrossingRate: Double
  }
  public init(provider: WakeWordModelProvider = WakeWordModelProvider(), pilot: WakeWordPilotConfiguration = .default) { self.provider = provider; self.pilot = pilot }
  public var availability: WakeWordDetectorAvailability {
    let p: WakeWordPermissionStatus
    switch AVCaptureDevice.authorizationStatus(for: .audio) { case .authorized: p = .granted; case .denied: p = .denied; case .restricted: p = .restricted; case .notDetermined: p = .notRequested; @unknown default: p = .unavailable }
    return WakeWordDetectorAvailability(available: provider.available, backendIdentifier: "coreml_temporal_features_pilot", permissionStatus: p)
  }
  public func start(configuration: WakeWordDetectorConfiguration, detectionHandler: @escaping @Sendable (WakeWordDetectionSignal) -> Void) throws {
    guard configuration.phraseKey == pilot.phraseKey else { throw BrokerError.invalidArguments }
    let localPredictor: TemporalWakeModelPredictor
    localPredictor = try TemporalWakeModelPredictor(model: provider.load())
    let localEngine = AVAudioEngine(); let input = localEngine.inputNode; let format = input.inputFormat(forBus: 0)
    guard format.sampleRate > 0, format.channelCount > 0, let target = AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1), let converter = AVAudioConverter(from: format, to: target) else { throw BrokerError.capabilityUnavailable }
    let auth = AVCaptureDevice.authorizationStatus(for: .audio); let granted: Bool
    if auth == .notDetermined {
      let sem = DispatchSemaphore(value: 0); var decision = false
      let request: () -> Void = {
        AVCaptureDevice.requestAccess(for: .audio) { value in
          decision = value; sem.signal()
        }
      }
      if Thread.isMainThread { request() } else { DispatchQueue.main.async(execute: request) }
      let result = sem.wait(timeout: .now() + 30)
      _ = result
      granted = decision
    } else { granted = auth == .authorized }
    guard granted else { throw BrokerError.permissionDenied }
    lock.lock(); generation += 1; let g = generation; buffer.reset(); pendingSamples = 0; positiveWindows = 0; triggerDiagnostics.removeAll(keepingCapacity: true); previousFeatures = nil; pendingAudio = nil; workerScheduled = false; predictor = localPredictor; handler = detectionHandler; engine = localEngine; active = true; metrics = Metrics(); metricsTimer?.cancel(); metricsTimer = Self.makeMetricsTimer(queue: queue) { [weak self] in self?.logMetrics() }; metricsTimer?.resume(); Self.logger.info("wake_runtime_input sample_rate_hz=\(format.sampleRate, privacy: .public) channels=\(format.channelCount, privacy: .public) converter_output_sample_rate_hz=16000 converter_output_channels=1") ; lock.unlock()
    input.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] pcm, _ in
      guard let self, let copy = try? Self.copyBuffer(pcm) else { return }
      self.lock.lock(); self.metrics.audioCallbacks += 1; let wasPending = self.pendingAudio != nil; self.pendingAudio = (copy, converter, target, g); if wasPending { self.metrics.droppedWork += 1 }; self.metrics.pendingWork = 1; self.metrics.maximumBacklog = max(self.metrics.maximumBacklog, 1); let schedule = !self.workerScheduled; self.workerScheduled = true; self.lock.unlock()
      if schedule { self.queue.async { self.drainLatestAudio() } }
    }
    do { try localEngine.start(); lock.lock(); metrics.engineStarts += 1; lock.unlock() } catch {
      let nsError = error as NSError
      Self.logger.debug("wake_runtime_engine_start_failed error_domain=\(nsError.domain, privacy: .public) error_code=\(nsError.code, privacy: .public) description=\(nsError.localizedDescription, privacy: .public)")
      input.removeTap(onBus: 0); stop(reason: "error"); throw BrokerError.internalFailure
    }
  }
  public func stop() { stop(reason: "explicit_stop") }
  private func stop(reason: String) {
    lock.lock(); generation += 1; active = false; pendingAudio = nil; workerScheduled = false; let local = engine; engine = nil; predictor = nil; handler = nil; buffer.reset(); pendingSamples = 0; positiveWindows = 0; metrics.pendingWork = 0; metrics.engineStops += local == nil ? 0 : 1; let timer = metricsTimer; metricsTimer = nil; lock.unlock()
    timer?.cancel()
    if local != nil { logMetrics(stopReason: reason, reset: false) }
    local?.inputNode.removeTap(onBus: 0); local?.stop()
  }
  private static func copyBuffer(_ source: AVAudioPCMBuffer) throws -> AVAudioPCMBuffer {
    guard let copy = AVAudioPCMBuffer(pcmFormat: source.format, frameCapacity: source.frameLength) else { throw BrokerError.capabilityUnavailable }
    copy.frameLength = source.frameLength
    copy.mutableAudioBufferList.pointee = source.audioBufferList.pointee
    guard let sourceData = source.floatChannelData, let destinationData = copy.floatChannelData else { throw BrokerError.capabilityUnavailable }
    for channel in 0..<Int(source.format.channelCount) { destinationData[channel].assign(from: sourceData[channel], count: Int(source.frameLength)) }
    return copy
  }
  private func convertAndConsume(_ source: AVAudioPCMBuffer, converter: AVAudioConverter, target: AVAudioFormat, generation: Int) {
    let started = ProcessInfo.processInfo.systemUptime
    let ratio = target.sampleRate / source.format.sampleRate
    let capacity = AVAudioFrameCount(ceil(Double(source.frameLength) * ratio)) + 16
    guard let output = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { return }
    var supplied = false; var error: NSError?
    let status = converter.convert(to: output, error: &error) { _, status in
      if supplied { status.pointee = .noDataNow; return nil }
      supplied = true; status.pointee = .haveData; return source
    }
    guard status != .error, error == nil, output.frameLength > 0, let channel = output.floatChannelData?[0] else {
      lock.lock(); metrics.pendingWork = max(0, metrics.pendingWork - 1); metrics.computeTime += ProcessInfo.processInfo.systemUptime - started; lock.unlock()
      return
    }
    let values = Array(UnsafeBufferPointer(start: channel, count: Int(output.frameLength))).map(Double.init)
    Self.logger.debug("wake_runtime_converted_buffer samples=\(values.count, privacy: .public)")
    lock.lock(); metrics.convertedBuffers += 1; lock.unlock()
    consume(values, generation: generation)
    lock.lock(); metrics.pendingWork = max(0, metrics.pendingWork - 1); metrics.computeTime += ProcessInfo.processInfo.systemUptime - started; lock.unlock()
  }
  private func drainLatestAudio() {
    lock.lock(); guard let work = pendingAudio else { workerScheduled = false; metrics.pendingWork = 0; lock.unlock(); return }; pendingAudio = nil; lock.unlock()
    convertAndConsume(work.0, converter: work.1, target: work.2, generation: work.3)
    lock.lock(); let more = pendingAudio != nil && active; if !more { workerScheduled = false; metrics.pendingWork = 0 }; lock.unlock()
    if more { queue.async { [weak self] in self?.drainLatestAudio() } }
  }
  private func consume(_ samples: [Double], generation: Int) {
    lock.lock(); guard active, self.generation == generation else { lock.unlock(); return }; buffer.append(samples); pendingSamples += samples.count; let infer = pendingSamples >= pilot.inferenceHopSamples; if infer { pendingSamples = 0 }; let values = buffer.samples; let model = predictor; lock.unlock()
    guard infer, values.count >= pilot.inferenceWindowSamples, let model else { if infer { lock.lock(); metrics.skippedWindows += 1; lock.unlock() }; return }
    let startIndex = values.count - pilot.inferenceWindowSamples
    let endIndex = values.count
    let inferenceSamples = Array(values[startIndex..<endIndex])
    let features: [Double]
    let featureStarted = ProcessInfo.processInfo.systemUptime
    do { features = try extractor.extract(samples: inferenceSamples) } catch { return }
    lock.lock(); metrics.featureDuration += ProcessInfo.processInfo.systemUptime - featureStarted; metrics.inferenceAttempts += 1; lock.unlock()
    let inferenceStarted = ProcessInfo.processInfo.systemUptime
    let prediction: TemporalWakePrediction
    do { prediction = try model.predict(features: features) } catch { return }
    let inferenceElapsed = ProcessInfo.processInfo.systemUptime - inferenceStarted
    let logit = log(prediction.probability / max(1e-12, 1 - prediction.probability))
    let correlation = previousFeatures.map { Self.correlation($0, features) }
    lock.lock(); metrics.successfulInferences += 1; metrics.inferenceDuration += inferenceElapsed; metrics.maximumInferenceDuration = max(metrics.maximumInferenceDuration, inferenceElapsed); metrics.inferenceSequence += 1; let sequence = metrics.inferenceSequence; let relativeTime = Date().timeIntervalSince(metrics.intervalStart); let streak = prediction.probability >= self.pilot.confidenceThreshold ? positiveWindows + 1 : 0; previousFeatures = features; lock.unlock()
    Self.logger.info("wake_window_diagnostic sequence=\(sequence, privacy: .public) relative_s=\(relativeTime, privacy: .public) sample_count=\(values.count, privacy: .public) probability=\(prediction.probability, privacy: .public) logit=\(logit, privacy: .public) positive=\(prediction.probability >= self.pilot.confidenceThreshold, privacy: .public) streak=\(streak, privacy: .public) feature_correlation=\(correlation ?? -1, privacy: .public) standardized_feature_norm=unavailable standardized_max_abs_z=unavailable standardized_gt3=unavailable standardized_gt5=unavailable top_contributors=unavailable")
    let audioStats = Self.audioDiagnostics(inferenceSamples)
    let diagnostic = RuntimeTriggerDiagnostic(inferenceSequence: sequence, relativeTimestamp: relativeTime, features: features, coreMLProbability: prediction.probability, coreMLLogit: logit, rms: audioStats.0, peakAbsoluteAmplitude: audioStats.1, meanDC: audioStats.2, zeroCrossingRate: audioStats.3)
    lock.lock(); guard active, self.generation == generation else { lock.unlock(); return }; positiveWindows = prediction.probability >= pilot.confidenceThreshold ? positiveWindows + 1 : 0; if positiveWindows > 0 { triggerDiagnostics.append(diagnostic); if triggerDiagnostics.count > pilot.consecutiveWindows { triggerDiagnostics.removeFirst() } } else { triggerDiagnostics.removeAll(keepingCapacity: true) }; let shouldPersist = positiveWindows == pilot.consecutiveWindows; let records = triggerDiagnostics; lock.unlock()
    if shouldPersist { Self.persistRuntimeAudit(records) }
    lock.lock(); guard active, self.generation == generation, positiveWindows >= pilot.consecutiveWindows else { lock.unlock(); return }; active = false; self.generation += 1; let callback = handler; handler = nil; let local = engine; engine = nil; predictor = nil; buffer.reset(); positiveWindows = 0; metrics.engineStops += local == nil ? 0 : 1; let timer = metricsTimer; metricsTimer = nil; lock.unlock(); timer?.cancel(); logMetrics(stopReason: "wake_detected", reset: false); local?.inputNode.removeTap(onBus: 0); local?.stop(); callback?(WakeWordDetectionSignal(confidence: prediction.probability))
  }

  private static func makeMetricsTimer(queue: DispatchQueue, handler: @escaping () -> Void) -> DispatchSourceTimer {
    let timer = DispatchSource.makeTimerSource(queue: queue)
    timer.schedule(deadline: .now() + 10, repeating: 60)
    timer.setEventHandler(handler: handler)
    return timer
  }

  private func logMetrics(stopReason: String? = nil, reset: Bool = true) {
    if stopReason == nil { lock.lock(); let stillActive = active; lock.unlock(); guard stillActive else { return } }
    lock.lock(); let value = metrics; lock.unlock()
    let elapsed = max(Date().timeIntervalSince(value.intervalStart), 1)
    let averageInference = value.successfulInferences == 0 ? 0 : value.inferenceDuration / Double(value.successfulInferences)
    let averageFeature = value.inferenceAttempts == 0 ? 0 : value.featureDuration / Double(value.inferenceAttempts)
    let reasonField = stopReason.map { " stop_reason=\($0)" } ?? ""
    Self.logger.info("wake_runtime_summary active_duration_s=\(elapsed, privacy: .public) audio_callbacks_s=\(Double(value.audioCallbacks) / elapsed, privacy: .public) converted_buffers_s=\(Double(value.convertedBuffers) / elapsed, privacy: .public) inference_attempts_s=\(Double(value.inferenceAttempts) / elapsed, privacy: .public) successful_inferences=\(value.successfulInferences, privacy: .public) avg_inference_ms=\(averageInference * 1000, privacy: .public) max_inference_ms=\(value.maximumInferenceDuration * 1000, privacy: .public) avg_feature_ms=\(averageFeature * 1000, privacy: .public) pending_work=\(value.pendingWork, privacy: .public) max_backlog=\(value.maximumBacklog, privacy: .public) dropped_work=\(value.droppedWork, privacy: .public) skipped_windows=\(value.skippedWindows, privacy: .public) engine_starts=\(value.engineStarts, privacy: .public) engine_stops=\(value.engineStops, privacy: .public) compute_s_per_min=\(value.computeTime / elapsed * 60, privacy: .public)\(reasonField, privacy: .public)")
    if reset { lock.lock(); metrics = Metrics(); lock.unlock() }
  }

  private static func correlation(_ lhs: [Double], _ rhs: [Double]) -> Double {
    guard lhs.count == rhs.count, !lhs.isEmpty else { return -1 }
    let a = lhs.reduce(0, +) / Double(lhs.count); let b = rhs.reduce(0, +) / Double(rhs.count)
    let numerator = zip(lhs, rhs).reduce(0) { $0 + ($1.0 - a) * ($1.1 - b) }
    let denominator = sqrt(lhs.reduce(0) { $0 + pow($1 - a, 2) } * rhs.reduce(0) { $0 + pow($1 - b, 2) })
    return denominator == 0 ? 1 : numerator / denominator
  }

  private static func audioDiagnostics(_ samples: [Double]) -> (Double, Double, Double, Double) {
    guard !samples.isEmpty else { return (0, 0, 0, 0) }
    let mean = samples.reduce(0, +) / Double(samples.count)
    let rms = sqrt(samples.reduce(0) { $0 + $1 * $1 } / Double(samples.count))
    let peak = samples.map(abs).max() ?? 0
    let crossings = zip(samples.dropFirst(), samples).reduce(0) { $0 + (($1.0 >= 0) != ($1.1 >= 0) ? 1 : 0) }
    return (rms, peak, mean, Double(crossings) / Double(max(1, samples.count - 1)))
  }

  private static func persistRuntimeAudit(_ records: [RuntimeTriggerDiagnostic]) {
    guard records.count == 3 else { return }
    let fm = FileManager.default
    let root = ProcessInfo.processInfo.environment["CAUCO_WAKE_RUNTIME_AUDIT_DIR"].map(URL.init(fileURLWithPath:)) ?? fm.homeDirectoryForCurrentUser.appendingPathComponent("wake-model/runtime-audit")
    do { try fm.createDirectory(at: root, withIntermediateDirectories: true); let url = root.appendingPathComponent("trigger-\(Int(Date().timeIntervalSince1970)).json"); let payload: [String: Any] = ["created_at": ISO8601DateFormatter().string(from: Date()), "records": try JSONSerialization.jsonObject(with: JSONEncoder().encode(records))]; let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]); try data.write(to: url, options: .atomic); logger.info("wake_runtime_audit_persisted path=\(url.path, privacy: .public) records=3") } catch { logger.error("wake_runtime_audit_persist_failed error=\(String(describing: error), privacy: .public)") }
  }
}
