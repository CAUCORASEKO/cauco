import Foundation

public enum WakeWordPermissionStatus: String, Sendable {
  case denied
  case granted
  case notRequested = "not_requested"
  case restricted
  case unavailable
}

public enum WakeWordListeningState: String, Sendable {
  case detected
  case disabled
  case error
  case listening
  case stopped
  case unavailable
}

public struct WakeWordDetectorAvailability: Equatable, Sendable {
  public let available: Bool
  public let backendIdentifier: String
  public let permissionStatus: WakeWordPermissionStatus

  public init(
    available: Bool, backendIdentifier: String,
    permissionStatus: WakeWordPermissionStatus
  ) {
    self.available = available
    self.backendIdentifier = backendIdentifier
    self.permissionStatus = permissionStatus
  }
}

public struct WakeWordDetectorConfiguration: Equatable, Sendable {
  public let phraseKey: String
  public let locale: String

  public init(phraseKey: String, locale: String) {
    self.phraseKey = phraseKey
    self.locale = locale
  }
}

public struct WakeWordDetectionSignal: Equatable, Sendable {
  public let confidence: Double?

  public init(confidence: Double? = nil) {
    self.confidence = confidence
  }
}

public protocol WakeWordDetectorGateway: AnyObject, Sendable {
  var availability: WakeWordDetectorAvailability { get }
  func start(
    configuration: WakeWordDetectorConfiguration,
    detectionHandler: @escaping @Sendable (WakeWordDetectionSignal) -> Void
  ) throws
  func stop()
}

public final class UnavailableWakeWordDetectorGateway: WakeWordDetectorGateway,
  @unchecked Sendable
{
  public let availability = WakeWordDetectorAvailability(
    available: false,
    backendIdentifier: "native_coreml_unconfigured",
    permissionStatus: .unavailable)

  public init() {}

  public func start(
    configuration _: WakeWordDetectorConfiguration,
    detectionHandler _: @escaping @Sendable (WakeWordDetectionSignal) -> Void
  ) throws {
    throw BrokerError.capabilityUnavailable
  }

  public func stop() {}
}

public struct WakeWordDetectedEvent: Equatable, Sendable {
  public let eventReference: String
  public let phraseKey: String
  public let detectedAt: Date
  public let confidence: Double?
}

public struct WakeWordCapabilitySnapshot: Equatable, Sendable {
  public let available: Bool
  public let state: WakeWordListeningState
  public let permissionStatus: WakeWordPermissionStatus
  public let detectorBackend: String
  public let phraseKey: String?
  public let active: Bool

  var brokerResult: [String: BrokerJSONValue] {
    [
      "available": .boolean(available),
      "state": .string(state.rawValue),
      "permission_status": .string(permissionStatus.rawValue),
      "detector_backend": .string(detectorBackend),
      "phrase_key": phraseKey.map(BrokerJSONValue.string) ?? .null,
      "active": .boolean(active),
    ]
  }
}

public final class WakeWordCapabilityService: @unchecked Sendable {
  private let detector: WakeWordDetectorGateway
  private let eventHandler: @Sendable (WakeWordDetectedEvent) -> Void
  private let makeEventReference: @Sendable () -> String
  private let now: @Sendable () -> Date
  private let lock = NSLock()
  private var active = false
  private var configuration: WakeWordDetectorConfiguration?
  private var generation = 0
  private var phraseKey: String?
  private var state: WakeWordListeningState

  public init(
    detector: WakeWordDetectorGateway = UnavailableWakeWordDetectorGateway(),
    eventHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void = { _ in },
    now: @escaping @Sendable () -> Date = { Date() },
    makeEventReference: @escaping @Sendable () -> String = {
      "wakeevt_\(UUID().uuidString.lowercased().replacingOccurrences(of: "-", with: ""))"
    }
  ) {
    self.detector = detector
    self.eventHandler = eventHandler
    self.now = now
    self.makeEventReference = makeEventReference
    state = detector.availability.available ? .disabled : .unavailable
  }

  public func status() -> WakeWordCapabilitySnapshot {
    lock.lock()
    defer { lock.unlock() }
    return snapshotLocked()
  }

  @discardableResult
  public func start(configuration: WakeWordDetectorConfiguration) throws
    -> WakeWordCapabilitySnapshot
  {
    guard detector.availability.available else { throw BrokerError.capabilityUnavailable }
    lock.lock()
    if active {
      guard self.configuration == configuration else {
        lock.unlock()
        throw BrokerError.invalidArguments
      }
      let snapshot = snapshotLocked()
      lock.unlock()
      return snapshot
    }
    generation += 1
    let currentGeneration = generation
    active = true
    self.configuration = configuration
    phraseKey = configuration.phraseKey
    state = .listening
    lock.unlock()

    do {
      try detector.start(configuration: configuration) { [weak self] signal in
        self?.detected(signal, generation: currentGeneration)
      }
    } catch {
      lock.lock()
      if generation == currentGeneration {
        generation += 1
        active = false
        state = .error
      }
      lock.unlock()
      detector.stop()
      throw error
    }
    return status()
  }

  @discardableResult
  public func stop() -> WakeWordCapabilitySnapshot {
    lock.lock()
    generation += 1
    active = false
    state = detector.availability.available ? .stopped : .unavailable
    lock.unlock()
    detector.stop()
    return status()
  }

  private func detected(_ signal: WakeWordDetectionSignal, generation callbackGeneration: Int) {
    lock.lock()
    guard active, generation == callbackGeneration, let detectedPhraseKey = phraseKey else {
      lock.unlock()
      return
    }
    generation += 1
    active = false
    state = .detected
    lock.unlock()

    // One-shot capture is stopped before any event can leave the native detector boundary.
    detector.stop()
    let confidence = signal.confidence.flatMap { (0...1).contains($0) ? $0 : nil }
    eventHandler(
      WakeWordDetectedEvent(
        eventReference: makeEventReference(), phraseKey: detectedPhraseKey,
        detectedAt: now(), confidence: confidence))
  }

  private func snapshotLocked() -> WakeWordCapabilitySnapshot {
    let availability = detector.availability
    return WakeWordCapabilitySnapshot(
      available: availability.available, state: state,
      permissionStatus: availability.permissionStatus,
      detectorBackend: availability.backendIdentifier, phraseKey: phraseKey, active: active)
  }
}
