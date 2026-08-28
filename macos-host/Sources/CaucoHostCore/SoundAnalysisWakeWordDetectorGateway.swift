import AVFoundation
import CoreML
import Foundation
import SoundAnalysis

/// The first local detector is deliberately a bounded pilot.  It is unavailable until a
/// verified SoundAnalysis-compatible model is placed in the host bundle.
public struct WakeWordPilotConfiguration: Sendable {
  public static let `default` = WakeWordPilotConfiguration()
  public let phraseKey = "hola_cauco"
  public let modelLabel = "hola_cauco"
  public let confidenceThreshold = 0.85
  public let consecutiveWindows = 3
}

public final class WakeWordModelProvider: @unchecked Sendable {
  private let modelURL: URL?
  public init(modelURL: URL? = Bundle.main.url(forResource: "HolaCauco", withExtension: "mlmodelc", subdirectory: "WakeWord")) { self.modelURL = modelURL }
  public var available: Bool { modelURL != nil }
  public func load() throws -> MLModel {
    guard let modelURL else { throw BrokerError.capabilityUnavailable }
    return try MLModel(contentsOf: modelURL, configuration: MLModelConfiguration())
  }
}

public final class SoundAnalysisWakeWordDetectorGateway: WakeWordDetectorGateway, @unchecked Sendable {
  private let provider: WakeWordModelProvider
  private let pilot: WakeWordPilotConfiguration
  private let lock = NSLock()
  private var engine: AVAudioEngine?
  private var analyzer: SNAudioStreamAnalyzer?
  private var observer: WakeObserver?
  private var handler: (@Sendable (WakeWordDetectionSignal) -> Void)?
  private var positives = 0
  private var active = false

  public init(provider: WakeWordModelProvider = WakeWordModelProvider(), pilot: WakeWordPilotConfiguration = .default) { self.provider = provider; self.pilot = pilot }
  public var availability: WakeWordDetectorAvailability {
    let permission: WakeWordPermissionStatus
    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .authorized: permission = .granted
    case .denied: permission = .denied
    case .restricted: permission = .restricted
    case .notDetermined: permission = .notRequested
    @unknown default: permission = .unavailable
    }
    return WakeWordDetectorAvailability(available: provider.available, backendIdentifier: "avfoundation_soundanalysis_pilot", permissionStatus: permission)
  }
  public func start(configuration: WakeWordDetectorConfiguration, detectionHandler: @escaping @Sendable (WakeWordDetectionSignal) -> Void) throws {
    guard configuration.phraseKey == pilot.phraseKey else { throw BrokerError.invalidArguments }
    guard provider.available else { throw BrokerError.capabilityUnavailable }
    let authorization = AVCaptureDevice.authorizationStatus(for: .audio)
    let granted: Bool
    if authorization == .notDetermined {
      let semaphore = DispatchSemaphore(value: 0)
      var decision = false
      AVCaptureDevice.requestAccess(for: .audio) { allowed in decision = allowed; semaphore.signal() }
      _ = semaphore.wait(timeout: .now() + 30)
      granted = decision
    }
    else { granted = authorization == .authorized }
    guard granted else { throw BrokerError.permissionDenied }
    let model = try provider.load()
    let request = try SNClassifySoundRequest(mlModel: model)
    let localEngine = AVAudioEngine(); let input = localEngine.inputNode
    let format = input.inputFormat(forBus: 0)
    guard format.sampleRate > 0, format.channelCount > 0 else { throw BrokerError.capabilityUnavailable }
    let localAnalyzer = SNAudioStreamAnalyzer(format: format)
    let localObserver = WakeObserver(label: pilot.modelLabel, threshold: pilot.confidenceThreshold, consecutive: pilot.consecutiveWindows) { [weak self] signal in self?.detected(signal) }
    try localAnalyzer.add(request, withObserver: localObserver)
    input.installTap(onBus: 0, bufferSize: 2048, format: format) { buffer, time in localAnalyzer.analyze(buffer, atAudioFramePosition: time.sampleTime) }
    do { try localEngine.start() } catch { input.removeTap(onBus: 0); throw BrokerError.internalFailure }
    lock.lock(); engine=localEngine; analyzer=localAnalyzer; observer=localObserver; handler=detectionHandler; positives=0; active=true; lock.unlock()
  }
  public func stop() { lock.lock(); let local=engine; engine=nil; analyzer=nil; observer=nil; handler=nil; positives=0; active=false; lock.unlock(); local?.inputNode.removeTap(onBus: 0); local?.stop() }
  private func detected(_ signal: WakeWordDetectionSignal) { lock.lock(); guard active else { lock.unlock(); return }; active=false; let callback=handler; lock.unlock(); stop(); callback?(signal) }
}

private final class WakeObserver: NSObject, SNResultsObserving {
  let label: String; let threshold: Double; let consecutive: Int; let callback: (WakeWordDetectionSignal) -> Void; var count=0
  init(label: String, threshold: Double, consecutive: Int, callback: @escaping (WakeWordDetectionSignal)->Void) { self.label=label; self.threshold=threshold; self.consecutive=consecutive; self.callback=callback }
  func request(_ request: SNRequest, didProduce result: SNResult) {
    guard let classification = result as? SNClassificationResult, let item = classification.classifications.first(where: {$0.identifier == label}) else { return }
    count = item.confidence >= threshold ? count + 1 : 0
    if count >= consecutive { count=0; callback(WakeWordDetectionSignal(confidence: item.confidence)) }
  }
  func request(_ request: SNRequest, didFailWithError error: Error) { count=0 }
  func requestDidComplete(_ request: SNRequest) { count=0 }
}
