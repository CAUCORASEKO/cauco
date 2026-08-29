import AVFoundation
import CoreML
import Foundation

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
  private let provider: WakeWordModelProvider; private let pilot: WakeWordPilotConfiguration; private let lock = NSLock(); private let queue = DispatchQueue(label: "cauco.wake.coreml-analysis")
  private var engine: AVAudioEngine?; private var handler: (@Sendable (WakeWordDetectionSignal) -> Void)?; private var buffer = BoundedMonoAudioBuffer(); private var predictor: TemporalWakeModelPredictor?; private var positiveWindows = 0; private var pendingSamples = 0; private var generation = 0; private var active = false
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
    lock.lock(); generation += 1; let g = generation; buffer.reset(); pendingSamples = 0; positiveWindows = 0; predictor = localPredictor; handler = detectionHandler; engine = localEngine; active = true; lock.unlock()
    input.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] pcm, _ in
      guard let self, let copy = try? Self.copyBuffer(pcm) else { return }
      self.queue.async { self.convertAndConsume(copy, converter: converter, target: target, generation: g) }
    }
    do { try localEngine.start() } catch { input.removeTap(onBus: 0); stop(); throw BrokerError.internalFailure }
  }
  public func stop() { lock.lock(); generation += 1; active = false; let local = engine; engine = nil; predictor = nil; handler = nil; buffer.reset(); pendingSamples = 0; positiveWindows = 0; lock.unlock(); local?.inputNode.removeTap(onBus: 0); local?.stop() }
  private static func copyBuffer(_ source: AVAudioPCMBuffer) throws -> AVAudioPCMBuffer {
    guard let copy = AVAudioPCMBuffer(pcmFormat: source.format, frameCapacity: source.frameLength) else { throw BrokerError.capabilityUnavailable }
    copy.frameLength = source.frameLength
    copy.mutableAudioBufferList.pointee = source.audioBufferList.pointee
    guard let sourceData = source.floatChannelData, let destinationData = copy.floatChannelData else { throw BrokerError.capabilityUnavailable }
    for channel in 0..<Int(source.format.channelCount) { destinationData[channel].assign(from: sourceData[channel], count: Int(source.frameLength)) }
    return copy
  }
  private func convertAndConsume(_ source: AVAudioPCMBuffer, converter: AVAudioConverter, target: AVAudioFormat, generation: Int) {
    let ratio = target.sampleRate / source.format.sampleRate
    let capacity = AVAudioFrameCount(ceil(Double(source.frameLength) * ratio)) + 16
    guard let output = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { return }
    var supplied = false; var error: NSError?
    let status = converter.convert(to: output, error: &error) { _, status in
      if supplied { status.pointee = .noDataNow; return nil }
      supplied = true; status.pointee = .haveData; return source
    }
    guard status != .error, error == nil, output.frameLength > 0, let channel = output.floatChannelData?[0] else {
      return
    }
    let values = Array(UnsafeBufferPointer(start: channel, count: Int(output.frameLength))).map(Double.init)
    consume(values, generation: generation)
  }
  private func consume(_ samples: [Double], generation: Int) {
    lock.lock(); guard active, self.generation == generation else { lock.unlock(); return }; buffer.append(samples); pendingSamples += samples.count; let infer = pendingSamples >= pilot.inferenceHopSamples; if infer { pendingSamples = 0 }; let values = buffer.samples; let model = predictor; lock.unlock()
    guard infer, values.count >= pilot.inferenceWindowSamples, let model else { return }
    let startIndex = values.count - pilot.inferenceWindowSamples
    let endIndex = values.count
    let inferenceSamples = Array(values[startIndex..<endIndex])
    let features: [Double]
    do { features = try TemporalWakeFeatureExtractor().extract(samples: inferenceSamples) } catch { return }
    let prediction: TemporalWakePrediction
    do { prediction = try model.predict(features: features) } catch { return }
    lock.lock(); guard active, self.generation == generation else { lock.unlock(); return }; positiveWindows = prediction.probability >= pilot.confidenceThreshold ? positiveWindows + 1 : 0; lock.unlock()
    lock.lock(); guard active, self.generation == generation, positiveWindows >= pilot.consecutiveWindows else { lock.unlock(); return }; active = false; self.generation += 1; let callback = handler; handler = nil; let local = engine; engine = nil; predictor = nil; buffer.reset(); positiveWindows = 0; lock.unlock(); local?.inputNode.removeTap(onBus: 0); local?.stop(); callback?(WakeWordDetectionSignal(confidence: prediction.probability))
  }
}
