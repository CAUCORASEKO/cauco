import SwiftUI
import AppKit
import CaucoHostCore

@main struct CaucoHostApp: App {
    @StateObject private var model = HostModel()
    var body: some Scene {
        WindowGroup("Cauco") { ContentView(model: model).frame(minWidth: 520, minHeight: 360) }
    }
}

@MainActor final class HostModel: ObservableObject {
    @Published var coreStatus = "stopped"
    @Published var contacts = "not requested"
    @Published var diagnostic = "Ready. No private data has been accessed."
    let coreURL = URL(string: "http://127.0.0.1:8765")!
    private let permission = NativeContactsPermissionGateway()
    private var process: Process?
    private let lifecycle = CoreLifecycleRules()

    init() { refreshContacts() }
    func refreshContacts() { contacts = String(describing: permission.authorizationState()) }
    func requestContacts() {
        diagnostic = "Waiting for macOS Contacts decision…"
        permission.requestAccess { [weak self] state in self?.contacts = String(describing: state); self?.diagnostic = "Contacts state updated; no contacts were read." }
    }
    func startCore() {
        guard lifecycle.canStart(ownedProcessExists: process != nil) else { diagnostic = "Core is already owned by this host."; return }
        do {
            let resolved = try resolveCorePython(repository: URL(fileURLWithPath: FileManager.default.currentDirectoryPath))
            let configuration = CoreLaunchConfiguration(executable: resolved.executable, repository: resolved.repository)
            let p = Process(); p.executableURL = configuration.executable; p.arguments = configuration.arguments; p.currentDirectoryURL = resolved.repository
            try p.run(); process = p; coreStatus = "starting"; diagnostic = "Core starting; waiting for localhost health."; Task { await waitForHealth(configuration.url, process: p) }
        } catch { process = nil; coreStatus = "unavailable"; diagnostic = boundedDiagnostic("Unable to start Core: \(error.localizedDescription)") }
    }
    private func waitForHealth(_ url: URL, process: Process) async {
        for _ in 0..<20 {
            if let (_, response) = try? await URLSession.shared.data(from: url.appendingPathComponent("health")), let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) { coreStatus = "online"; diagnostic = "Core is online on localhost."; return }
            try? await Task.sleep(for: .milliseconds(250))
        }
        if coreStatus == "starting" { coreStatus = "unavailable"; diagnostic = "Core did not become healthy within the bounded startup timeout."; if self.process === process { process.terminate(); self.process = nil } }
    }
    func stopCore() { guard let p = process, lifecycle.canStop(ownedProcessExists: true) else { return }; p.terminate(); process = nil; coreStatus = "stopped"; diagnostic = "Owned Core process stopped." }
    func openDashboard() { NSWorkspace.shared.open(coreURL) }
}

struct ContentView: View {
    @ObservedObject var model: HostModel
    var body: some View { VStack(alignment: .leading, spacing: 16) {
        Text("Cauco Host").font(.largeTitle.bold()); Text("Native permission owner and local Core companion").foregroundStyle(.secondary)
        GroupBox("Status") { VStack(alignment: .leading, spacing: 8) { Label("Host: online", systemImage: "desktopcomputer"); Label("Core: \(model.coreStatus)", systemImage: "circle.fill"); Text("Core URL: \(model.coreURL.absoluteString)"); Text("Apple Contacts: \(model.contacts)") }.frame(maxWidth: .infinity, alignment: .leading).padding(4) }
        HStack { Button("Request Contacts Access", action: model.requestContacts); Button(model.coreStatus == "starting" || model.coreStatus == "online" ? "Stop Core" : "Start Core", action: model.coreStatus == "starting" || model.coreStatus == "online" ? model.stopCore : model.startCore); Button("Open Core", action: model.openDashboard).disabled(model.coreStatus != "online") }
        Text(model.diagnostic).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
        Spacer(); Text("No contact records are displayed or accessed by this host.").font(.footnote).foregroundStyle(.secondary)
    }.padding(24) }
}
