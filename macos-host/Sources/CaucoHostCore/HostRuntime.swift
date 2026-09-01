import Foundation

@MainActor public final class HostRuntime {
  public private(set) var isRunning = false
  public private(set) var isShutdown = false
  private let configuration: HostRuntimeConfiguration
  private let processFactory: HostRuntimeProcessFactory
  private let brokerFactory: HostRuntimeBrokerFactory
  private let localWakeHandler: @Sendable (WakeWordDetectedEvent) -> Void
  private let updateHandler: @MainActor (HostRuntimeUpdate) -> Void
  private let terminator: OwnedCoreProcessTerminator
  private var process: HostRuntimeProcess?
  private var broker: HostRuntimeBrokerServer?
  private var wakeTransport: CaucoWakeEventTransport?
  private var healthTask: Task<Void, Never>?
  private var generation = 0
  private var stoppedEmitted = false

  public init(
    configuration: HostRuntimeConfiguration,
    processFactory: HostRuntimeProcessFactory,
    brokerFactory: HostRuntimeBrokerFactory,
    localWakeHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void = { _ in },
    updateHandler: @escaping @MainActor (HostRuntimeUpdate) -> Void = { _ in },
    terminator: OwnedCoreProcessTerminator = OwnedCoreProcessTerminator()
  ) {
    self.configuration = configuration; self.processFactory = processFactory
    self.brokerFactory = brokerFactory; self.localWakeHandler = localWakeHandler
    self.updateHandler = updateHandler; self.terminator = terminator
  }

  public func start() {
    guard !isShutdown, !isRunning, process == nil else { return }
    generation += 1; let token = generation; stoppedEmitted = false; updateHandler(.starting)
    do {
      let transport = CaucoWakeEventTransport(socketURL: FileManager.default.temporaryDirectory.appendingPathComponent("cauco-wake-events-\(UUID().uuidString).sock"))
      let server = try brokerFactory.makeBrokerServer(
        coreWakeHandler: transport.send, localWakeHandler: localWakeHandler)
      try server.start(); broker = server; wakeTransport = transport; updateHandler(.brokerStarted)
      let child = try processFactory.makeProcess(configuration: configuration)
      child.onTermination { [weak self] in
        Task { @MainActor [weak self] in self?.terminated(token: token) }
      }
      process = child; try child.launch(); isRunning = true
      let snapshot = makeSnapshot(process: child, state: .starting)
      updateHandler(.processStarted(snapshot))
      healthTask = Task { [weak self] in await self?.pollHealth(token: token) }
    } catch { cleanupResources(); updateHandler(.failed(message: "Unable to start Core runtime.")) }
  }

  public func stop() {
    guard !isShutdown else { return }
    guard process != nil || broker != nil || wakeTransport != nil else { return }
    invalidate(); if let process { _ = terminator.stop(process) }; cleanupResources(); emitStopped()
  }

  public func shutdown() {
    guard !isShutdown else { return }
    isShutdown = true; invalidate(); if let process { _ = terminator.stop(process) }; cleanupResources(); emitStopped()
  }

  private func invalidate() { generation += 1; healthTask?.cancel(); healthTask = nil }
  private func emitStopped() { guard !stoppedEmitted else { return }; stoppedEmitted = true; updateHandler(.stopped) }
  private func cleanupResources() { broker?.stop(); broker = nil; wakeTransport = nil; process = nil; isRunning = false }

  private func terminated(token: Int) {
    guard !isShutdown, token == generation, process != nil else { return }
    healthTask?.cancel(); healthTask = nil
    guard let process else { return }
    var snapshot = makeSnapshot(process: process, state: .unavailable)
    snapshot.running = false; snapshot.terminationReason = process.diagnosticTerminationReason; snapshot.terminationStatus = process.terminationStatus
    cleanupResources(); updateHandler(.processExited(snapshot: snapshot, reason: process.diagnosticTerminationReason, status: process.terminationStatus))
  }

  private func makeSnapshot(process: CoreProcessDiagnostics, state: CoreLifecycleState) -> CoreLaunchDiagnosticSnapshot {
    CoreLaunchDiagnosticSnapshot(
      process: process, executable: configuration.executable, arguments: configuration.arguments,
      workingDirectory: configuration.workingDirectory, state: state
    )
  }

  private func pollHealth(token: Int) async {
    let started = Date()
    while !Task.isCancelled {
      guard token == generation, !isShutdown, let process else { return }
      var request = URLRequest(url: configuration.coreBaseURL.appendingPathComponent("health")); request.timeoutInterval = 1
      let healthy: Bool
      if let (data, response) = try? await URLSession.shared.data(for: request), let http = response as? HTTPURLResponse, http.statusCode == 200, let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any], object["status"] as? String == "ok" { healthy = true } else { healthy = false }
      guard token == generation, !isShutdown, self.process === process else { return }
      let elapsed = Int(Date().timeIntervalSince(started) * 1000)
      var snapshot = makeSnapshot(process: process, state: healthy ? .online : .starting)
      snapshot.latestHealthCheck = healthy ? "healthy" : "retry"
      updateHandler(.healthCheck(snapshot, healthy: healthy))
      if healthy {
        updateHandler(.healthy(snapshot))
        return
      }
      if configuration.healthPolicy.nextResult(processRunning: process.isRunning, elapsedMilliseconds: elapsed, probeHealthy: false) == .timedOut { return }
      try? await Task.sleep(for: .milliseconds(configuration.healthPolicy.retryMilliseconds))
    }
  }
}
