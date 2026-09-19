import AppKit
import CaucoHostCore
import Darwin
import SwiftUI

@MainActor final class CaucoHostAppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
  weak var model: HostModel?
  private var settingsController: NSWindowController?
  private var mainController: NSWindowController?
  private var terminationSignalSources: [DispatchSourceSignal] = []

  func applicationDidFinishLaunching(_ notification: Notification) {
    NSApplication.shared.setActivationPolicy(.regular)
    installTerminationSignalHandlers()
    showMainWindow()
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
    if settingsController == nil {
      let content = NSHostingController(rootView: SettingsView(model: model))
      let window = NSWindow(contentViewController: content)
      window.title = "Cauco Settings"
      window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
      window.setContentSize(NSSize(width: 620, height: 520))
      window.center()
      window.isReleasedWhenClosed = false
      window.restorationClass = nil
      window.delegate = self
      settingsController = NSWindowController(window: window)
    }
    settingsController?.showWindow(nil)
    settingsController?.window?.makeKeyAndOrderFront(nil)
    NSApplication.shared.activate(ignoringOtherApps: true)
  }

  func showMainWindow() {
    NSApplication.shared.setActivationPolicy(.regular)
    if mainController == nil {
      guard let model else { return }
      let content = NSHostingController(rootView: ConversationView(
        presentation: model.conversationPresentation,
        controller: model.conversationInteraction,
        handsFree: model.handsFreeService,
        showSettings: { [weak self] in self?.showSettingsWindow() }))
      let window = NSWindow(contentViewController: content)
      window.title = "Cauco"
      window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
      window.setContentSize(NSSize(width: 720, height: 700))
      window.center()
      window.isReleasedWhenClosed = false
      window.restorationClass = nil
      window.delegate = self
      mainController = NSWindowController(window: window)
    }
    mainController?.showWindow(nil)
    mainController?.window?.makeKeyAndOrderFront(nil)
    NSApplication.shared.activate(ignoringOtherApps: true)
  }

  func configureHandsFree(for model: HostModel) {
    model.handsFreeService = HostHandsFreeService(
      presentation: model.conversationPresentation,
      conversation: model.conversationInteraction,
      showConversation: { [weak self] in self?.showMainWindow() })
    // This arms only the local wake detector. Speech recognition starts after wake.
    model.handsFreeService?.restorePersistedWakeListening()
  }

  func windowWillClose(_ notification: Notification) {
    guard notification.object as? NSWindow === settingsController?.window ||
      notification.object as? NSWindow === mainController?.window else { return }
    DispatchQueue.main.async { [weak self] in
      guard let self else { return }
      let settingsVisible = self.settingsController?.window?.isVisible == true
      let mainVisible = self.mainController?.window?.isVisible == true
      if !settingsVisible && !mainVisible { NSApplication.shared.setActivationPolicy(.accessory) }
    }
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
  @StateObject private var model: HostModel

  init() {
    let model = HostModel()
    _model = StateObject(wrappedValue: model)
    appDelegate.model = model
    appDelegate.configureHandsFree(for: model)
    model.startCore()
  }

  var body: some Scene {
    MenuBarExtra("Cauco", systemImage: "waveform") {
      Button("Open Cauco") {
        showCauco()
      }
      Divider()
      Text("Status: \(model.coreStatus == "online" ? "Running" : model.coreStatus.capitalized)")
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
    appDelegate.showMainWindow()
    NSApplication.shared.activate(ignoringOtherApps: true)
    DispatchQueue.main.async {
      NSApp.windows.first(where: { $0.title == "Cauco" })?.makeKeyAndOrderFront(nil)
    }
  }
}

private final class ProductionBrokerFactory: HostRuntimeBrokerFactory {
  let permission: ContactsPermissionGateway
  private(set) var server: NativeBrokerTransportServer?
  init(permission: ContactsPermissionGateway) { self.permission = permission }
  func makeBrokerServer(coreWakeHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void,
                        localWakeHandler: @escaping @Sendable (WakeWordDetectedEvent) -> Void) throws -> HostRuntimeBrokerServer {
    let broker = NativeCapabilityBroker(permission: permission, wakeWordDetector: SoundAnalysisWakeWordDetectorGateway(),
      wakeWordEventHandler: coreWakeHandler, wakeWordLocalEventHandler: localWakeHandler)
    let value = try NativeBrokerTransportServer(broker: broker); server = value; return value
  }
}

private final class ProductionProcessFactory: HostRuntimeProcessFactory {
  private weak var brokerFactory: ProductionBrokerFactory?
  init(brokerFactory: ProductionBrokerFactory) { self.brokerFactory = brokerFactory }
  func makeProcess(configuration: HostRuntimeConfiguration) throws -> HostRuntimeProcess {
    let process = Process(); try process.configure(configuration: configuration)
    var environment = configuration.environment
    if let broker = brokerFactory?.server {
      environment["CAUCO_NATIVE_BROKER_SOCKET"] = broker.socketURL.path
      environment["CAUCO_NATIVE_BROKER_TOKEN"] = broker.token
    }
    process.environment = environment
    process.standardError = Pipe(); process.standardOutput = Pipe()
    return process
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
  let conversationPresentation = ConversationPresentationModel()
  lazy var conversationInteraction = ConversationInteractionController(coreURL: coreURL, presentation: conversationPresentation)
  @Published var handsFreeService: HostHandsFreeService?
  private let permission = NativeContactsPermissionGateway()
  private let calendarPermission = NativeCalendarPermissionGateway()
  private var runtime: HostRuntime?
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
    do {
      let resolved = try RepositoryConfiguration.resolve(
        workingDirectory: URL(fileURLWithPath: FileManager.default.currentDirectoryPath))
      let configuration = CoreLaunchConfiguration(
        executable: resolved.executable, repository: resolved.repository)
      let runtimeConfiguration = HostRuntimeConfiguration(executable: configuration.executable, arguments: configuration.arguments,
        workingDirectory: resolved.repository, environment: ProcessInfo.processInfo.environment,
        coreBaseURL: configuration.url)
      if runtime == nil {
        let brokerFactory = ProductionBrokerFactory(permission: permission)
        runtime = HostRuntime(configuration: runtimeConfiguration,
          processFactory: ProductionProcessFactory(brokerFactory: brokerFactory), brokerFactory: brokerFactory,
          updateHandler: { [weak self] update in self?.applyRuntimeUpdate(update) })
      }
      runtime?.start()
    } catch RepositoryResolutionError.unconfigured {
      coreStatus = "stopped"
      diagnostic = "Select the Cauco repository before starting Core."
    } catch {
      coreStatus = "unavailable"
      diagnostic = boundedDiagnostic("Unable to start Core: \(error.localizedDescription)")
    }
  }
  private func applyRuntimeUpdate(_ update: HostRuntimeUpdate) {
    switch update {
    case .starting: coreStatus = "starting"; diagnostic = "Core starting; waiting for localhost health."
    case .brokerStarted: break
    case .processStarted(let snapshot): launchDiagnostics = snapshot; hasOwnedProcess = true
    case .healthCheck(let snapshot, _): launchDiagnostics = snapshot
    case .healthy(let snapshot): launchDiagnostics = snapshot; coreStatus = "online"; diagnostic = "Core is online on localhost."
    case .processExited(let snapshot, _, let status): launchDiagnostics = snapshot; hasOwnedProcess = false; coreStatus = "unavailable"; diagnostic = "Core process exited unexpectedly (exit code \(status))."
    case .failed(let message): hasOwnedProcess = false; coreStatus = "unavailable"; diagnostic = message
    case .stopped: hasOwnedProcess = false; coreStatus = "stopped"; diagnostic = "Owned Core process stopped."
    }
  }
  func stopCore() {
    runtime?.stop()
  }

  func shutdownForHostTermination() {
    runtime?.shutdown()
  }
  func openDashboard() { NSWorkspace.shared.open(coreURL) }
}

struct SettingsView: View {
  @ObservedObject var model: HostModel
  private func statusColor(_ tone: VoiceActivationStatusTone) -> Color {
    switch tone { case .neutral: return .secondary; case .active: return .green; case .error: return .red }
  }
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
