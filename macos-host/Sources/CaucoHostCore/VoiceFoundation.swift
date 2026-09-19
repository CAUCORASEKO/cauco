import Foundation

public enum SpeechPermissionState: String, Sendable { case notDetermined, denied, restricted, authorized, unavailable }
public enum SpeechTranscriptionState: Equatable, Sendable { case idle, requestingPermission, listening, transcribing, completed, stopped, failed }
public enum SpeechSynthesisState: Equatable, Sendable { case idle, speaking, completed, stopped, failed }
public enum VoiceFoundationError: Error { case permissionDenied, onDeviceUnavailable, busy, noSpeechDetected }

@MainActor public protocol SpeechTranscriber: AnyObject {
  var permissionState: SpeechPermissionState { get }
  var onDeviceAvailable: Bool { get }
  var state: SpeechTranscriptionState { get }
  func start(locale: Locale, onTranscript: @escaping (String) -> Void, onError: @escaping (Error) -> Void)
  func stop()
}

@MainActor public protocol SpeechSynthesizer: AnyObject {
  var state: SpeechSynthesisState { get }
  func speak(_ text: String, locale: Locale, onComplete: @escaping () -> Void, onError: @escaping (Error) -> Void)
  func stop()
}
