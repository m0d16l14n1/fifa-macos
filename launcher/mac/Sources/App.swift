// FIFA 19 launcher: a SwiftUI window with a sidebar. The game is fifa19 beside this program in the app's
// Contents/MacOS; its settings are ~/Library/Application Support/FIFA 19/fifa19.toml (Settings.swift lists the
// ones offered here), its log ~/Library/Logs/FIFA 19/fifa19.log.

import AppKit
import Combine
import SwiftUI

enum Page: String, CaseIterable, Identifiable {
    case play = "Play", quickMatch = "Quick Match", graphics = "Graphics", controls = "Controls",
         mods = "Mods", gameFiles = "Game Files", about = "About"
    var id: String { rawValue }
    var symbol: String {
        switch self {
        case .play: return "play.circle"
        case .quickMatch: return "sportscourt"
        case .graphics: return "display"
        case .controls: return "gamecontroller"
        case .mods: return "puzzlepiece.extension"
        case .gameFiles: return "externaldrive"
        case .about: return "info.circle"
        }
    }
}

// Tests (FIFA19_LAUNCHER_PLAY=1): the game starts when the launcher has finished launching, with or without a
// window (macOS may restore none).
final class LauncherDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        guard Game.testEnv["FIFA19_LAUNCHER_PLAY"] == "1" else { return }
        if Game.testEnv["FIFA19_LAUNCHER_BACKGROUND"] == "1" { NSApp.setActivationPolicy(.accessory) }
        Task { @MainActor in Game.shared.play() }
    }
}

@main
struct LauncherApp: App {
    @NSApplicationDelegateAdaptor(LauncherDelegate.self) private var delegate
    @StateObject private var game = Game.shared
    @State private var page: Page? = Page(rawValue: ProcessInfo.processInfo.environment["FIFA19_LAUNCHER_PAGE"] ?? "") ?? .play

    var body: some Scene {
        WindowGroup("FIFA 19") {
            NavigationSplitView {
                List(Page.allCases, selection: $page) { p in
                    Label(p.rawValue, systemImage: p.symbol).tag(p)
                }
                .navigationSplitViewColumnWidth(min: 160, ideal: 180)
            } detail: {
                Group {
                    switch page ?? .play {
                    case .play: PlayPage()
                    case .quickMatch: QuickMatchPage()
                    case .graphics: SettingsPage(title: "Graphics", settings: Setting.graphics)
                    case .controls: SettingsPage(title: "Controls", settings: Setting.controls)
                    case .mods: ModsPage()
                    case .gameFiles: GameFilesPage()
                    case .about: AboutPage()
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .padding(24)
            }
            .environmentObject(game)
            .frame(minWidth: 760, minHeight: 520)
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
                game.reload()
            }
            .onAppear { Snapshot.takeIfAsked() }
        }
        .windowResizability(.contentMinSize)
    }
}

// Tests and docs: FIFA19_LAUNCHER_SNAPSHOT=<file.png> draws the launcher's window (the page FIFA19_LAUNCHER_PAGE
// opens) into that file and quits. The window is the launcher's own, drawn by it: no screen recording permission,
// and it never takes focus (a background app while it does this).
enum Snapshot {
    static func takeIfAsked() {
        guard let path = ProcessInfo.processInfo.environment["FIFA19_LAUNCHER_SNAPSHOT"], !path.isEmpty else { return }
        NSApp.setActivationPolicy(.accessory)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            guard let view = NSApp.windows.first(where: { $0.isVisible })?.contentView,
                  let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { exit(1) }
            view.cacheDisplay(in: view.bounds, to: rep)
            let written = (try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))) != nil
            exit(written ? 0 : 1)
        }
    }
}

struct PlayPage: View {
    @EnvironmentObject var game: Game
    @State private var logTail = ""
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("FIFA 19").font(.largeTitle.bold())
            Text("Xbox 360, recompiled for Apple silicon and drawn natively with Metal.")
                .foregroundStyle(.secondary)
            HStack(spacing: 12) {
                if game.running == nil {
                    Button { game.play() } label: { Label("Play", systemImage: "play.fill").frame(minWidth: 90) }
                        .keyboardShortcut(.defaultAction)
                        .controlSize(.large)
                        .disabled(!game.programInstalled || !game.gameInstalled)
                } else {
                    Button(role: .destructive) { game.stop() } label: {
                        Label("Stop", systemImage: "stop.fill").frame(minWidth: 90)
                    }.controlSize(.large)
                    ProgressView().controlSize(.small)
                    Text("Running").foregroundStyle(.secondary)
                }
            }
            if !game.programInstalled {
                Notice(text: "The game's program is missing from \(game.paths.programFolder.path).", warning: true)
            } else if !game.gameInstalled {
                Notice(text: "Choose your extracted game, or extract it, in Game Files.", warning: true)
            }
            if let exit = game.lastExit { Notice(text: exit, warning: true) }
            GroupBox("While playing") {
                VStack(alignment: .leading, spacing: 8) {
                    Toggle("Metal performance HUD", isOn: $game.metalHud)
                    Toggle("Keep the window in the background (it never takes focus)", isOn: $game.backgroundWindow)
                    Toggle("Metal API validation (slow; for rendering bugs)", isOn: $game.metalValidation)
                    HStack {
                        Text("Extra options")
                        TextField("--log_level=debug", text: $game.extraArguments).textFieldStyle(.roundedBorder)
                    }
                }.padding(6)
            }
            GroupBox("Log") {
                ScrollView {
                    Text(logTail.isEmpty ? "No log yet." : logTail)
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(minHeight: 120)
                HStack {
                    Button("Show in Finder") { NSWorkspace.shared.activateFileViewerSelecting([game.paths.log]) }
                    Spacer()
                }
            }
        }
        .onReceive(timer) { _ in logTail = Game.tail(of: game.paths.log, lines: 12) }
        .onAppear {
            logTail = Game.tail(of: game.paths.log, lines: 12)
        }
    }
}

// Quick Match: straight into a match, the CPU against the CPU, at the stadium, time of day and weather chosen here
// (EA's own auto match, fifa19_quick_match): for trying conditions, or a benchmark, in about a minute.
struct QuickMatchPage: View {
    @EnvironmentObject var game: Game

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Quick Match").font(.title.bold())
            Text("Straight into a match, no intro or menus: the CPU plays both teams. For trying a stadium, "
                 + "a time of day and the weather in about a minute.").foregroundStyle(.secondary)
            HStack(spacing: 12) {
                if game.running == nil {
                    Button { game.play(extra: ["--fifa19_quick_match=true"]) } label: {
                        Label("Start the match", systemImage: "sportscourt.fill").frame(minWidth: 140)
                    }
                    .controlSize(.large)
                    .disabled(!game.programInstalled || !game.gameInstalled)
                } else {
                    Button(role: .destructive) { game.stop() } label: {
                        Label("Stop", systemImage: "stop.fill").frame(minWidth: 90)
                    }.controlSize(.large)
                    Text("Running").foregroundStyle(.secondary)
                }
            }
            Form {
                ForEach(Setting.quickMatch) { setting in SettingRow(setting: setting) }
            }
            .formStyle(.grouped)
        }
    }
}

struct Notice: View {
    let text: String
    var warning = false
    var body: some View {
        Label(text, systemImage: warning ? "exclamationmark.triangle" : "info.circle")
            .foregroundStyle(warning ? Color.orange : Color.secondary)
            .textSelection(.enabled)
    }
}

struct GameFilesPage: View {
    @EnvironmentObject var game: Game

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Game Files").font(.title.bold())
            Text("Bring your own FIFA 19 (Xbox 360, title 454109F9). Nothing of the game comes with this app.")
                .foregroundStyle(.secondary)
            GroupBox {
                VStack(alignment: .leading, spacing: 8) {
                    if game.gameInstalled {
                        Label("Game found: \(game.gameFolder)", systemImage: "checkmark.circle")
                            .foregroundStyle(.green)
                    } else {
                        Label(game.gameFolder.isEmpty ? "No game chosen." : "No default.xex in \(game.gameFolder).",
                              systemImage: "questionmark.circle")
                    }
                    HStack {
                        Button("Choose the extracted game…") { chooseFolder() }
                        Button("Extract a Games on Demand package…") { choosePackage() }
                            .disabled(game.extracting || game.paths.extractor == nil)
                    }
                    if game.extracting { ProgressView().controlSize(.small) }
                    if !game.extractStatus.isEmpty { Text(game.extractStatus).foregroundStyle(.secondary) }
                }.padding(6)
            }
            Text("Saves and settings: \(game.paths.support.path)").font(.caption).foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.message = "The folder with default.xex"
        if panel.runModal() == .OK, let url = panel.url { game.gameFolder = url.path }
    }

    private func choosePackage() {
        let open = NSOpenPanel()
        open.canChooseFiles = true
        open.message = "The package's header file (in 454109F9/00007000, with its .data folder beside it)"
        guard open.runModal() == .OK, let package = open.url else { return }
        let save = NSOpenPanel()
        save.canChooseDirectories = true
        save.canChooseFiles = false
        save.canCreateDirectories = true
        save.message = "Where to put the game (about 6.6 GB)"
        guard save.runModal() == .OK, let folder = save.url else { return }
        game.extract(package: package, into: folder.appendingPathComponent("FIFA 19"))
    }
}

struct AboutPage: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("About").font(.title.bold())
            Text("FIFA 19 for macOS: a ReXGlue static recompilation of the Xbox 360 game, with a native Metal "
                + "renderer, MetalFX upscaling, Core Audio output and Game Controller input.")
            Text("FIFA, EA SPORTS and the game's content belong to Electronic Arts. This project is not affiliated "
                + "with or endorsed by EA or Microsoft.").foregroundStyle(.secondary)
            Text("Version \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "dev")")
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}

struct ModsPage: View {
    @EnvironmentObject var game: Game
    @State private var folders: [String] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Mods").font(.largeTitle.bold())
            Text("A mod is a folder of the game's files, laid out as on the disc (data/db/fifa_ng_db.db, "
                 + "data/sceneassets/kit/...). A file the game has is replaced, a new one added; your game "
                 + "files stay as they are. Names and other text go in strings/eng_us.csv (stringid,text). Mods go on in "
                 + "name order: where two change the same file or string, the later wins.")
                .foregroundStyle(.secondary)
            // No .fixedSize(horizontal: false, vertical: true) here: on macOS 27 it left the whole window blank
            // (sidebar too) and the launcher unusable. The text wraps without it.
            HStack {
                Button {
                    try? FileManager.default.createDirectory(at: game.paths.mods, withIntermediateDirectories: true)
                    NSWorkspace.shared.open(game.paths.mods)
                } label: { Label("Open the Mods Folder", systemImage: "folder") }
                Button { folders = game.modFolders() } label: { Label("Refresh", systemImage: "arrow.clockwise") }
            }
            GroupBox {
                if folders.isEmpty {
                    Text("No mods in \(game.paths.mods.path).").foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(folders, id: \.self) { name in
                            Toggle(name, isOn: Binding(
                                get: { !game.disabledMods.contains(name) },
                                set: { on in
                                    if on { game.disabledMods.remove(name) } else { game.disabledMods.insert(name) }
                                }))
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            if !game.modStatus.isEmpty { Text("Last start: \(game.modStatus)").foregroundStyle(.secondary) }
        }
        .onAppear { folders = game.modFolders() }
    }
}
