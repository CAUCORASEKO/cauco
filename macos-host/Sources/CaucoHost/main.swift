import AppKit
import CaucoHostCore
import Darwin
import SwiftUI

@MainActor final class CaucoHostAppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
  weak var model: HostModel?
  private var windowController: NSWindowController?
  private var terminationSignalSources: [DispatchSourceSignal] = []

  func applicationDidFinishLaunching(_ notification: Notification) {
    NSApplication.shared.setActivationPolicy(.accessory)
    installTerminationSignalHandlers()
  }

  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    false
  }

  func applicationShouldOpenUntitledFile(_ sender: NSApplication) -> Bool {
    false
  }

  func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
    .terminateNow
  }

  func requestQuit() {
    NSApplication.shared.terminate(nil)
  }

  func showSettingsWindow() {
    guard let model else { return }
    NSApplication.shared.setActivationPolicy(.regular)
    if windowController == nil {
      let content = NSHostingController(rootView: ContentView(model: model))
      let window = NSWindow(contentViewController: content)
      window.title = "Cauco Settings"
      window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
      window.setContentSize(NSSize(width: 620, height: 520))
      window.center()
      window.isReleasedWhenClosed = false
      window.restorationClass = nil
      window.delegate = self
      windowController = NSWindowController(window: window)
    }
    windowController?.showWindow(nil)
    windowController?.window?.makeKeyAndOrderFront(nil)
    NSApplication.shared.activate(ignoringOtherApps: true)
  }

  func windowWillClose(_ notification: Notification) {
    guard notification.object as? NSWindow === windowController?.window else { return }
    NSApplication.shared.setActivationPolicy(.accessory)
  }

  func applicationWillTerminate(_ notification: Notification) {
    model?.shutdownForHostTermination()
    removeTerminationSignalHandlers()
  }

  private func installTerminationSignalHandlers() {
    for terminationSignal in [SIGINT, SIGTERM] {
      signal(terminationSignal, SIG_IGN)
      let source = DispatchSource.makeSignalSource(signal: terminationSignal, queue: .main)
      source.setEventHandler { [weak self] in
        self?.requestQuit()
      }
      source.resume()
      terminationSignalSources.append(source)
    }
  }

  private func removeTerminationSignalHandlers() {
    for source in terminationSignalSources { source.cancel() }
    terminationSignalSources.removeAll()
    signal(SIGINT, SIG_DFL)
    signal(SIGTERM, SIG_DFL)
  }
}

@main struct CaucoHostApp: App {
  @NSApplicationDelegateAdaptor(CaucoHostAppDelegate.self) private var appDelegate
  @StateObject private var model = HostModel()

  init() {
    let residentModel = HostModel()
    residentModel.startCore()
    _model = StateObject(wrappedValue: residentModel)
    appDelegate.model = residentModel
  }

  var body: some Scene {
    MenuBarExtra("Cauco", systemImage: "waveform") {
      Button("Open Cauco") {
        showCauco()
      }
      Divider()
      Text("Status: \(model.coreStatus == "online" ? "Running" : model.coreStatus.capitalized)")
      Toggle("Launch at Login", isOn: Binding(
        get: { model.launchAtLoginStatus == .enabled },
        set: { model.setLaunchAtLogin($0) }))
      if model.launchAtLoginStatus == .requiresApproval {
        Text("Approval required in System Settings")
      } else if model.launchAtLoginStatus == .failed {
        Text("Launch at Login could not be changed")
      }
      Divider()
      Button("Quit Cauco") { appDelegate.requestQuit() }
    }
    .commands {
      CommandGroup(replacing: .appTermination) {
        Button("Quit Cauco") { appDelegate.requestQuit() }
          .keyboardShortcut("q")
      }
    }
  }

  private func showCauco() {
    appDelegate.showSettingsWindow()
    NSApplication.shared.activate(ignoringOtherApps: true)
    DispatchQueue.main.async {
      NSApp.windows.first(where: { $0.title == "Cauco" })?.makeKeyAndOrderFront(nil)
    }
  }
}

@MainActor final class HostModel: ObservableObject {
  @Published var coreStatus = "stopped"
  @Published var contacts = "not requested"
  @Published var calendar = "not requested"
  @Published var diagnostic = "Ready. No private data has been accessed."
  @Published var repositoryPath = "Not configured"
  @Published var repositoryValidation = "Repository path is not configured."
  @Published private(set) var launchAtLoginStatus: LaunchAtLoginStatus
  @Published private(set) var hasOwnedProcess = false
  @Published var launchDiagnostics: CoreLaunchDiagnosticSnapshot?
  let coreURL = URL(string: "http://127.0.0.1:8765")!
  private let permission = NativeContactsPermissionGateway()
  private let calendarPermission = NativeCalendarPermissionGateway()
  private var process: Process?
  private var brokerServer: NativeBrokerTransportServer?
  private var wakeEventTransport: CaucoWakeEventTransport?
  private let lifecycle = CoreLifecycleRules()
  private let processTerminator = OwnedCoreProcessTerminator()
  private let launchAtLogin = LaunchAtLoginService()

  init() {
    launchAtLoginStatus = launchAtLogin.status
    refreshContacts()
    refreshCalendar()
    refreshRepository()
  }
  func setLaunchAtLogin(_ enabled: Bool) {
    launchAtLoginStatus = enabled ? launchAtLogin.enable() : launchAtLogin.disable()
  }
  deinit {
    if let process { _ = processTerminator.stop(process) }
    brokerServer?.stop()
  }
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
      let eventPath = FileManager.default.temporaryDirectory.appendingPathComponent("cauco-wake-events-\(UUID().uuidString).sock")
      let eventTransport = CaucoWakeEventTransport(socketURL: eventPath)
      let brokerServer = try NativeBrokerTransportServer(
        broker: NativeCapabilityBroker(permission: permission, wakeWordDetector: SoundAnalysisWakeWordDetectorGateway(), wakeWordEventHandler: eventTransport.send))
      try brokerServer.start()
      self.brokerServer = brokerServer
      self.wakeEventTransport = eventTransport
      let p = Process()
      p.executableURL = configuration.executable
      p.arguments = configuration.arguments
      p.currentDirectoryURL = resolved.repository
      var environment = ProcessInfo.processInfo.environment
      environment["CAUCO_NATIVE_BROKER_SOCKET"] = brokerServer.socketURL.path
      environment["CAUCO_NATIVE_BROKER_TOKEN"] = brokerServer.token
      environment["CAUCO_WAKE_EVENT_SOCKET"] = eventPath.path
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
          let previousStatus = self.coreStatus
          self.hasOwnedProcess = false
          self.process = nil
          self.brokerServer?.stop()
          self.brokerServer = nil
          self.coreStatus = "unavailable"
          self.launchDiagnostics?.lifecycleState = .unavailable

          if previousStatus == "starting" {
            self.diagnostic =
              "Core process exited before becoming healthy (exit code \(terminated.terminationStatus))."
          } else {
            self.diagnostic =
              "Core process exited unexpectedly (exit code \(terminated.terminationStatus))."
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
    let result = processTerminator.stop(p)
    brokerServer?.stop()
    brokerServer = nil
    if result == .stillRunning {
      coreStatus = "unavailable"
      launchDiagnostics?.lifecycleState = .unavailable
      diagnostic = "Owned Core process did not stop; Host retained process ownership."
    } else {
      process = nil
      hasOwnedProcess = false
      coreStatus = "stopped"
      launchDiagnostics?.running = false
      launchDiagnostics?.lifecycleState = .stopped
      diagnostic = "Owned Core process stopped."
    }
  }

  func shutdownForHostTermination() {
    if let process { _ = processTerminator.stop(process) }
    brokerServer?.stop()
    brokerServer = nil
    process = nil
    hasOwnedProcess = false
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
      GroupBox("Application") {
        VStack(alignment: .leading, spacing: 8) {
          Toggle("Start Cauco automatically when I log in", isOn: Binding(
            get: { model.launchAtLoginStatus == .enabled },
            set: { model.setLaunchAtLogin($0) }))
          if model.launchAtLoginStatus == .requiresApproval {
            Text("macOS requires approval in System Settings.").font(.caption)
          } else if model.launchAtLoginStatus == .failed {
            Text("macOS did not change the Launch at Login setting.").font(.caption)
          }
        }
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
