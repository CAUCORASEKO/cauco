import Foundation

public enum NativeHandsFreeState: String, Equatable, Sendable {
  case disabled, waitingForWake, wakeDetected, requestingSpeechPermission
  case listening, transcribing, thinking, speaking, confirmingClose, rearming, error
}

public enum NativeHandsFreeTransitionError: Error, Equatable {
  case invalidTransition(from: NativeHandsFreeState, to: NativeHandsFreeState)
}

public enum NativeHandsFreeStateMachine {
  public static func canTransition(from: NativeHandsFreeState, to: NativeHandsFreeState) -> Bool {
    switch (from, to) {
    case (.disabled, .waitingForWake),
         (.disabled, .requestingSpeechPermission),
         (.waitingForWake, .wakeDetected),
         (.wakeDetected, .requestingSpeechPermission),
         (.requestingSpeechPermission, .listening),
         (.listening, .transcribing),
         (.transcribing, .thinking),
         (.thinking, .speaking),
         (.listening, .confirmingClose),
         (.transcribing, .confirmingClose),
         (.speaking, .confirmingClose),
         (.speaking, .listening),
         (.confirmingClose, .listening),
         (.confirmingClose, .speaking),
         (.speaking, .rearming),
         (.rearming, .waitingForWake),
         (.waitingForWake, .disabled),
         (_, .error),
         (.wakeDetected, .disabled), (.requestingSpeechPermission, .disabled),
         (.listening, .disabled), (.transcribing, .disabled), (.thinking, .disabled),
         (.speaking, .disabled), (.rearming, .disabled), (.error, .disabled):
      return true
    default:
      return false
    }
  }

  public static func transition(
    _ state: NativeHandsFreeState, to next: NativeHandsFreeState
  ) throws -> NativeHandsFreeState {
    guard canTransition(from: state, to: next) else {
      throw NativeHandsFreeTransitionError.invalidTransition(from: state, to: next)
    }
    return next
  }
}

public final class NativeHandsFreeGeneration: @unchecked Sendable {
  private let lock = NSLock(); private var value = 0
  public init() {}
  public func advance() { lock.lock(); value += 1; lock.unlock() }
  public func current() -> Int { lock.lock(); defer { lock.unlock() }; return value }
  public func isCurrent(_ token: Int) -> Bool { current() == token }
}

public protocol NativeWakeListener: AnyObject {
  func start(locale: String, onDetection: @escaping (WakeWordDetectedEvent) -> Void) throws
  func stop()
}

public protocol ConversationResponding: AnyObject {
  func respond(instruction: String, useReasoning: Bool, completion: @escaping (Result<String, Error>) -> Void)
  func cancel()
}

public protocol HandsFreePresentation: AnyObject {
  func showConversation()
  func updateHandsFree(state: NativeHandsFreeState, transcript: String?, response: String?)
}

public protocol NativeHandsFreeCoordinating: AnyObject {
  var state: NativeHandsFreeState { get }
  var handsFreeEnabled: Bool { get }
  func enable(locale: String)
  func disable()
  func shutdown()
}
