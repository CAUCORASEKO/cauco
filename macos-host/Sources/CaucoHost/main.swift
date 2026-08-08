import AppKit
import CaucoHostCore
import SwiftUI

@main struct CaucoHostApp: App {
  @StateObject private var model = HostModel()
  var body: some Scene {
    WindowGroup("Cauco") { ContentView(model: model).frame(minWidth: 520, minHeight: 360) }
  }
}

@MainActor final class HostModel: ObservableObject {
  @Published var coreStatus = "stopped"
  @Published var contacts = "not requested"
  @Published var calendar = "not requested"
  @Published var diagnostic = "Ready. No private data has been accessed."
  @Published var repositoryPath = "Not configured"
  @Published var repositoryValidation = "Repository path is not configured."
  @Published private(set) var hasOwnedProcess = false
  @Published var launchDiagnostics: CoreLaunchDiagnosticSnapshot?
  let coreURL = URL(string: "http://127.0.0.1:8765")!
  private let permission = NativeContactsPermissionGateway()
  private let calendarPermission = NativeCalendarPermissionGateway()
  private var process: Process?
  private var brokerServer: NativeBrokerTransportServer?
  private let lifecycle = CoreLifecycleRules()

  init() {
    refreshContacts()
    refreshCalendar()
    refreshRepository()
  }
  deinit { brokerServer?.stop() }
  func refreshContacts() { contacts = String(describing: permission.authorizationState()) }
  func requestContacts() {
    diagnostic = "Waiting for macOS Contacts decision…"
    permission.requestAccess { [weak self] state in
      self?.contacts = String(describing: state)
      self?.diagnostic = "Contacts state updated; no contacts were read."
    }
  }
  func refreshCalendar() { calendar = String(describing: calendarPermission.authorizationState()) }
  func requestCalendar() {
    diagnostic = "Waiting for macOS Calendar decision…"
    calendarPermission.requestAccess { [weak self] state in
      self?.calendar = String(describing: state)
      self?.diagnostic = "Calendar state updated; no calendars or events were read."
    }
  }
  func refreshRepository() {
    do {
      let value = try RepositoryConfiguration.resolve(
        workingDirectory: URL(fileURLWithPath: FileManager.default.currentDirectoryPath))
      repositoryPath = value.repository.path
      repositoryValidation = "\(value.source.rawValue): \(value.repository.path)"
    } catch {
      let configuredPath = UserDefaults.standard.string(forKey: repositoryPathDefaultsKey)
      if let configuredPath, !configuredPath.isEmpty {
        repositoryPath = configuredPath
        repositoryValidation = "Invalid: \(boundedDiagnostic(error.localizedDescription))"
      } else if let environmentPath = ProcessInfo.processInfo.environment[
        repositoryPathEnvironmentKey], !environmentPath.isEmpty
      {
        repositoryPath = environmentPath
        repositoryValidation = "Invalid: \(boundedDiagnostic(error.localizedDescription))"
      } else {
        repositoryPath = "Not configured"
        repositoryValidation = "Repository path is not configured."
      }
    }
  }
  func chooseRepository() {
    let panel = NSOpenPanel()
    panel.canChooseFiles = false
    panel.canChooseDirectories = true
    panel.allowsMultipleSelection = false
    panel.prompt = "Choose Repository"
    guard panel.runModal() == .OK, let url = panel.url else { return }
    do {
      let config = try RepositoryConfiguration.validate(url)
      UserDefaults.standard.set(config.repository.path, forKey: repositoryPathDefaultsKey)
      refreshRepository()
      diagnostic = "Repository configured. Core was not started."
    } catch {
      diagnostic = boundedDiagnostic(error.localizedDescription)
      refreshRepository()
    }
  }
  func clearRepository() {
    UserDefaults.standard.removeObject(forKey: repositoryPathDefaultsKey)
    refreshRepository()
    diagnostic = "Repository configuration cleared."
  }
  func startCore() {
    guard lifecycle.canStart(ownedProcessExists: process != nil) else {
      diagnostic = "Core is already owned by this host."
      return
    }
    do {
      let resolved = try RepositoryConfiguration.resolve(
        workingDirectory: URL(fileURLWithPath: FileManager.default.currentDirectoryPath))
      let configuration = CoreLaunchConfiguration(
        executable: resolved.executable, repository: resolved.repository)
      let brokerServer = try NativeBrokerTransportServer(broker: NativeCapabilityBroker(permission: permission))
      try brokerServer.start()
      self.brokerServer = brokerServer
      let p = Process()
      p.executableURL = configuration.executable
      p.arguments = configuration.arguments
      p.currentDirectoryURL = resolved.repository
      var environment = ProcessInfo.processInfo.environment
      environment["CAUCO_NATIVE_BROKER_SOCKET"] = brokerServer.socketURL.path
      environment["CAUCO_NATIVE_BROKER_TOKEN"] = brokerServer.token
      p.environment = environment
      let stderr = Pipe()
      let stdout = Pipe()
      p.standardError = stderr
      p.standardOutput = stdout
      p.terminationHandler = { [weak self, weak p] terminated in
        let errorText =
          String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let outputText =
          String(data: stdout.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        Task { @MainActor [weak self, weak p] in
          guard let self, let p, self.process === p else { return }
          self.launchDiagnostics?.running = false
          self.launchDiagnostics?.terminationReason =
            terminated.terminationReason == .exit ? "exit" : "uncaughtSignal"
          self.launchDiagnostics?.terminationStatus = terminated.terminationStatus
          self.launchDiagnostics?.exitedBeforeHealth = self.coreStatus != "online"
          self.launchDiagnostics?.stderrTail = boundedDiagnosticTail(errorText, maxLines: 30)
          self.launchDiagnostics?.stdoutTail = boundedDiagnosticTail(outputText, maxLines: 10)
          self.hasOwnedProcess = false
          self.process = nil
          self.brokerServer?.stop()
          self.brokerServer = nil
          if self.coreStatus == "starting" {
            self.coreStatus = "unavailable"
            self.launchDiagnostics?.lifecycleState = .unavailable
            self.diagnostic =
              "Core process exited before becoming healthy (exit code \(terminated.terminationStatus))."
          }
        }
      }
      try p.run()
      process = p
      hasOwnedProcess = true
      coreStatus = "starting"
      launchDiagnostics = CoreLaunchDiagnosticSnapshot(
        process: p, configuration: configuration, state: .starting)
      diagnostic = "Core starting; waiting for localhost health."
      Task { await waitForHealth(configuration.url, process: p) }
    } catch RepositoryResolutionError.unconfigured {
      brokerServer?.stop()
      brokerServer = nil
      process = nil
      coreStatus = "stopped"
      diagnostic = "Select the Cauco repository before starting Core."
    } catch {
      brokerServer?.stop()
      brokerServer = nil
      process = nil
      hasOwnedProcess = false
      coreStatus = "unavailable"
      diagnostic = boundedDiagnostic("Unable to start Core: \(error.localizedDescription)")
    }
  }
  private func waitForHealth(_ url: URL, process: Process) async {
    let policy = CoreHealthPolicy()
    let started = Date()
    while process.isRunning {
      var request = URLRequest(url: url.appendingPathComponent("health"))
      request.timeoutInterval = 1.0
      var healthy = false
      if let (data, response) = try? await URLSession.shared.data(for: request),
        let http = response as? HTTPURLResponse, http.statusCode == 200,
        let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        object["status"] as? String == "ok"
      {
        healthy = true
      }
      if self.process === process {
        launchDiagnostics?.running = process.isRunning
        launchDiagnostics?.latestHealthCheck =
          healthy ? "HTTP 200 status=ok" : "retry: endpoint not ready"
      }
      let elapsed = Int(Date().timeIntervalSince(started) * 1000)
      switch policy.nextResult(
        processRunning: process.isRunning, elapsedMilliseconds: elapsed, probeHealthy: healthy)
      {
      case .healthy:
        if self.process === process, process.isRunning {
          coreStatus = "online"
          launchDiagnostics?.lifecycleState = .online
          diagnostic = "Core is online on localhost."
        }
        return
      case .processExited: return
      case .timedOut:
        if self.process === process, process.isRunning {
          coreStatus = "unavailable"
          launchDiagnostics?.lifecycleState = .unavailable
          diagnostic = "Process is still running but the health endpoint never became ready."
        }
        return
      case .retry: try? await Task.sleep(for: .milliseconds(policy.retryMilliseconds))
      }
    }
    if self.process === process, coreStatus == "starting" {
      coreStatus = "unavailable"
      launchDiagnostics?.lifecycleState = .unavailable
      hasOwnedProcess = false
      self.process = nil
      diagnostic = "Core process exited before becoming healthy."
    }
  }
  func stopCore() {
    guard let p = process, lifecycle.canStop(ownedProcessExists: true) else { return }
    p.terminate()
    brokerServer?.stop()
    brokerServer = nil
    process = nil
    hasOwnedProcess = false
    coreStatus = "stopped"
    launchDiagnostics?.lifecycleState = .stopped
    diagnostic = "Owned Core process stopped."
  }
  func openDashboard() { NSWorkspace.shared.open(coreURL) }
}

struct ContentView: View {
  @ObservedObject var model: HostModel
  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      Text("Cauco Host").font(.largeTitle.bold())
      Text("Native permission owner and local Core companion").foregroundStyle(.secondary)
      GroupBox("Status") {
        VStack(alignment: .leading, spacing: 8) {
          Label("Host: online", systemImage: "desktopcomputer")
          Label("Core: \(model.coreStatus)", systemImage: "circle.fill")
          Text("Core URL: \(model.coreURL.absoluteString)")
          Text("Apple Contacts: \(model.contacts)")
          Text("Apple Calendar: \(model.calendar)")
        }.frame(maxWidth: .infinity, alignment: .leading).padding(4)
      }
      GroupBox("Development Core") {
        VStack(alignment: .leading, spacing: 8) {
          Text("Repository: \(model.repositoryPath)").lineLimit(1)
          Text(model.repositoryValidation).font(.callout).foregroundStyle(.secondary)
          HStack {
            Button("Choose Repository…", action: model.chooseRepository)
            Button("Clear", action: model.clearRepository).disabled(
              model.repositoryPath == "Not configured")
          }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(4)
      }
      if let snapshot = model.launchDiagnostics {
        DisclosureGroup("Core Launch Diagnostics") {
          VStack(alignment: .leading, spacing: 4) {
            Text("PID: \(snapshot.pid) • running: \(snapshot.running ? "yes" : "no")")
            Text("Executable: \(snapshot.executable.path)")
            Text("Working directory: \(snapshot.workingDirectory.path)")
            Text("Arguments: \(snapshot.arguments.joined(separator: " "))")
            Text("Lifecycle: \(String(describing: snapshot.lifecycleState))")
            Text("Health: \(snapshot.latestHealthCheck)")
            if let reason = snapshot.terminationReason {
              Text("Termination: \(reason), status \(snapshot.terminationStatus ?? -1)")
            }
            if !snapshot.stderrTail.isEmpty {
              Text("stderr tail:\n\(snapshot.stderrTail.joined(separator: "\n"))")
            }
            if !snapshot.stdoutTail.isEmpty {
              Text("stdout tail:\n\(snapshot.stdoutTail.joined(separator: "\n"))")
            }
          }.font(.caption).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
            .padding(4)
        }
      }
      HStack {
        Button("Request Contacts Access", action: model.requestContacts)
        Button("Request Calendar Access", action: model.requestCalendar)
        Button(
          model.hasOwnedProcess ? "Stop Core" : "Start Core",
          action: model.hasOwnedProcess ? model.stopCore : model.startCore)
        Button("Open Core", action: model.openDashboard).disabled(model.coreStatus != "online")
      }
      Text(model.diagnostic).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
      Spacer()
      Text("No contact records are displayed or accessed by this host.").font(.footnote)
        .foregroundStyle(.secondary)
    }.padding(24)
  }
}
