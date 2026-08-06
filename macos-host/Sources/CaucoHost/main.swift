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

    init() { refreshContacts() }
    func refreshContacts() { contacts = String(describing: permission.authorizationState()) }
    func requestContacts() {
        diagnostic = "Waiting for macOS Contacts decision…"
        permission.requestAccess { [weak self] state in self?.contacts = String(describing: state); self?.diagnostic = "Contacts state updated; no contacts were read." }
    }
    func startCore() {
        guard process == nil else { diagnostic = "Core is already owned by this host."; return }
        let python = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(".venv/bin/python")
        let configuration = CoreLaunchConfiguration(executable: python, repository: URL(fileURLWithPath: FileManager.default.currentDirectoryPath))
        let p = Process(); p.executableURL = configuration.executable; p.arguments = configuration.arguments; p.currentDirectoryURL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        do { try p.run(); process = p; coreStatus = "starting"; diagnostic = "Core starting; waiting for localhost health."; Task { await waitForHealth(configuration.url) } } catch { coreStatus = "unavailable"; diagnostic = boundedDiagnostic("Unable to start Core: \(error.localizedDescription)") }
    }
    private func waitForHealth(_ url: URL) async {
        for _ in 0..<20 {
            if let (_, response) = try? await URLSession.shared.data(from: url.appendingPathComponent("health")), let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) { coreStatus = "online"; diagnostic = "Core is online on localhost."; return }
            try? await Task.sleep(for: .milliseconds(250))
        }
        if coreStatus == "starting" { coreStatus = "unavailable"; diagnostic = "Core did not become healthy within the bounded startup timeout."; process?.terminate(); process = nil }
    }
    func stopCore() { guard let p = process else { return }; p.terminate(); process = nil; coreStatus = "stopped"; diagnostic = "Owned Core process stopped." }
    func openDashboard() { NSWorkspace.shared.open(coreURL) }
}

struct ContentView: View {
    @ObservedObject var model: HostModel
    var body: some View { VStack(alignment: .leading, spacing: 16) {
        Text("Cauco Host").font(.largeTitle.bold()); Text("Native permission owner and local Core companion").foregroundStyle(.secondary)
        GroupBox("Status") { VStack(alignment: .leading, spacing: 8) { Label("Host: online", systemImage: "desktopcomputer"); Label("Core: \(model.coreStatus)", systemImage: "circle.fill"); Text("Core URL: \(model.coreURL.absoluteString)"); Text("Apple Contacts: \(model.contacts)") }.frame(maxWidth: .infinity, alignment: .leading).padding(4) }
        HStack { Button("Request Contacts Access", action: model.requestContacts); Button(model.coreStatus == "stopped" ? "Start Core" : "Stop Core", action: model.coreStatus == "stopped" ? model.startCore : model.stopCore); Button("Open Core", action: model.openDashboard).disabled(model.coreStatus != "online") }
        Text(model.diagnostic).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
        Spacer(); Text("No contact records are displayed or accessed by this host.").font(.footnote).foregroundStyle(.secondary)
    }.padding(24) }
}
