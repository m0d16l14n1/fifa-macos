// Where the game, its settings and its log are, and starting and stopping it.

import AppKit
import Foundation

struct Paths {
    /// The folder with the game's program (fifa19) and the ReXGlue libraries: the app's Contents/MacOS, or
    /// FIFA19_DIR when the launcher runs on its own.
    let programFolder: URL
    /// ~/Library/Application Support/FIFA 19: settings (fifa19.toml), saves and caches.
    let support: URL
    let logs: URL

    var program: URL { programFolder.appendingPathComponent("fifa19") }
    var config: URL { support.appendingPathComponent("fifa19.toml") }
    var log: URL { logs.appendingPathComponent("fifa19.log") }
    /// Mods: each a folder of files laid out like the disc (data/db/fifa_ng_db.db...), see docs/MODDING.md.
    var mods: URL { support.appendingPathComponent("Mods") }
    /// The game with the mods on: links to the game's files and the mods' (tools/modding/modgame.py).
    var moddedGame: URL { support.appendingPathComponent("Modded Game") }
    var modBuilder: URL? { Bundle.main.url(forResource: "modgame", withExtension: "py") }
    /// The Games on Demand extractor the app carries (scripts/extract_god.py).
    var extractor: URL? { Bundle.main.url(forResource: "extract_god", withExtension: "py") }

    static func current() -> Paths {
        let env = ProcessInfo.processInfo.environment
        let exeFolder = Bundle.main.executableURL?.deletingLastPathComponent() ?? URL(fileURLWithPath: ".")
        let programFolder = env["FIFA19_DIR"].map { URL(fileURLWithPath: $0) } ?? exeFolder
        let home = FileManager.default.homeDirectoryForCurrentUser
        let support = env["FIFA19_SUPPORT"].map { URL(fileURLWithPath: $0) }
            ?? home.appendingPathComponent("Library/Application Support/FIFA 19")
        return Paths(programFolder: programFolder, support: support,
                     logs: home.appendingPathComponent("Library/Logs/FIFA 19"))
    }
}

@MainActor
final class Game: ObservableObject {
    static let shared = Game()
    let paths = Paths.current()
    @Published private(set) var config = TomlFile(text: "")
    @Published private(set) var running: Process?
    @Published var lastExit: String?
    @Published var extracting = false
    @Published var extractStatus = ""

    // The launcher's own preferences, not the game's settings.
    @Published var metalHud = UserDefaults.standard.object(forKey: "metalHud") as? Bool ?? true {
        didSet { UserDefaults.standard.set(metalHud, forKey: "metalHud") }
    }
    @Published var metalValidation = UserDefaults.standard.bool(forKey: "metalValidation") {
        didSet { UserDefaults.standard.set(metalValidation, forKey: "metalValidation") }
    }
    @Published var backgroundWindow = UserDefaults.standard.bool(forKey: "backgroundWindow") {
        didSet { UserDefaults.standard.set(backgroundWindow, forKey: "backgroundWindow") }
    }
    @Published var extraArguments = UserDefaults.standard.string(forKey: "extraArguments") ?? "" {
        didSet { UserDefaults.standard.set(extraArguments, forKey: "extraArguments") }
    }
    /// The extracted game (the folder with default.xex). Passed on the command line: the SDK resolves its
    /// paths before it reads fifa19.toml.
    @Published var gameFolder = UserDefaults.standard.string(forKey: "gameFolder") ?? "" {
        didSet { UserDefaults.standard.set(gameFolder, forKey: "gameFolder") }
    }

    /// Mods turned off in the Mods page (by folder name); a mod put in the Mods folder is on.
    @Published var disabledMods = Set(UserDefaults.standard.stringArray(forKey: "disabledMods") ?? []) {
        didSet { UserDefaults.standard.set(Array(disabledMods).sorted(), forKey: "disabledMods") }
    }
    @Published var modStatus = ""

    /// The mods' folders, in the order they go on (a later one wins where two change the same file).
    func modFolders() -> [String] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: paths.mods.path)) ?? []
        return names.filter { name in
            var folder: ObjCBool = false
            return !name.hasPrefix(".")
                && FileManager.default.fileExists(atPath: paths.mods.appendingPathComponent(name).path, isDirectory: &folder)
                && folder.boolValue
        }.sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    }

    /// The game folder to run: the game itself, or the modded game when mods are on (built afresh each time:
    /// it is only links, a second or so). nil when the mods could not be put on (modStatus says why).
    func gameRoot(_ base: String) -> String? {
        let mods = modFolders().filter { !disabledMods.contains($0) }
        guard !mods.isEmpty else { modStatus = ""; return base }
        guard let builder = paths.modBuilder else { modStatus = "This app has no mod builder."; return nil }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = ["-I", builder.path, "build", "--game", base, "--out", paths.moddedGame.path]
            + mods.map { paths.mods.appendingPathComponent($0).path }
        let output = Pipe()
        process.standardOutput = output
        process.standardError = output
        do { try process.run() } catch {
            modStatus = "Could not start python3: \(error.localizedDescription)"
            return nil
        }
        let text = String(decoding: output.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
        process.waitUntilExit()
        let lines = text.split(separator: "\n")
        modStatus = (lines.last.map(String.init) ?? "").replacingOccurrences(of: paths.moddedGame.path + ": ", with: "")
        guard process.terminationStatus == 0 else {
            modStatus = "The mods could not be put on: " + text.trimmingCharacters(in: .whitespacesAndNewlines)
            return nil
        }
        return paths.moddedGame.path
    }

    init() {
        try? FileManager.default.createDirectory(at: paths.support, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: paths.logs, withIntermediateDirectories: true)
        reload()
    }

    func reload() {
        config = TomlFile(text: (try? String(contentsOf: paths.config, encoding: .utf8)) ?? "")
    }

    func value(_ key: String) -> TomlValue? { config.value(key) }

    /// Sets a setting; `nil` (or its default) removes the line, so the game's default applies.
    func set(_ key: String, _ value: TomlValue?, default fallback: TomlValue? = nil) {
        reload()  // the game's own "save settings" may have changed the file meanwhile
        var file = config
        file.set(key, value == fallback ? nil : value)
        do {
            try file.text.write(to: paths.config, atomically: true, encoding: .utf8)
            config = file
        } catch {
            lastExit = "Could not save \(paths.config.path): \(error.localizedDescription)"
        }
    }

    var gameInstalled: Bool {
        !gameFolder.isEmpty && FileManager.default.fileExists(atPath: gameFolder + "/default.xex")
    }
    var programInstalled: Bool { FileManager.default.isExecutableFile(atPath: paths.program.path) }

    /// Tests: FIFA19_LAUNCHER_ARGS adds options (after the Extra options), FIFA19_LAUNCHER_BACKGROUND=1 keeps the
    /// game's window in the background, FIFA19_GAME runs the game from another folder, and with FIFA19_LAUNCHER_PLAY=1 the launcher quits when the game does.
    static let testEnv = ProcessInfo.processInfo.environment

    func play(extra: [String] = []) {
        guard running == nil, programInstalled else { return }
        let process = Process()
        process.executableURL = paths.program
        process.currentDirectoryURL = paths.logs  // stall reports land next to the log
        var arguments = ["--log_file=\(paths.log.path)"]
        // Tests may run another copy of the game (FIFA19_GAME: a folder of links with a changed file or two).
        let testGame = Game.testEnv["FIFA19_GAME"] ?? ""
        if !testGame.isEmpty || gameInstalled {
            guard let root = gameRoot(testGame.isEmpty ? gameFolder : testGame) else {
                lastExit = modStatus
                if Game.testEnv["FIFA19_LAUNCHER_PLAY"] == "1" { exit(1) }
                return
            }
            arguments.append("--game_data_root=\(root)")
        }
        arguments += extraArguments.split(separator: " ").map(String.init)
        arguments += (Game.testEnv["FIFA19_LAUNCHER_ARGS"] ?? "").split(separator: " ").map(String.init)
        arguments += extra
        process.arguments = arguments
        var env = ProcessInfo.processInfo.environment
        if metalHud { env["MTL_HUD_ENABLED"] = "1" }
        if metalValidation { env["MTL_DEBUG_LAYER"] = "1"; env["METAL_DEVICE_WRAPPER_TYPE"] = "1" }
        if backgroundWindow || Game.testEnv["FIFA19_LAUNCHER_BACKGROUND"] == "1" { env["SDL_MAC_BACKGROUND_APP"] = "1"; env["SDL_WINDOW_ACTIVATE_WHEN_SHOWN"] = "0" }
        process.environment = env
        process.terminationHandler = { [weak self] finished in
            let status = finished.terminationStatus, reason = finished.terminationReason
            Task { @MainActor in
                guard let self else { return }
                self.running = nil
                self.reload()
                if Game.testEnv["FIFA19_LAUNCHER_PLAY"] == "1" { exit(status == 0 ? 0 : 1) }
                if reason == .uncaughtSignal || status != 0 {
                    self.lastExit = "The game stopped (\(reason == .uncaughtSignal ? "signal" : "exit code") \(status)). "
                        + "Its log: \(self.paths.log.path)"
                } else {
                    self.lastExit = nil
                }
            }
        }
        do {
            try process.run()
            running = process
            lastExit = nil
        } catch {
            lastExit = "Could not start \(paths.program.path): \(error.localizedDescription)"
        }
    }

    func stop() { running?.terminate() }

    /// Extracts a Games on Demand package (its header file; the .data folder beside it) into `target`.
    func extract(package: URL, into target: URL) {
        guard let extractor = paths.extractor, !extracting else { return }
        extracting = true
        extractStatus = "Extracting… (about 6.6 GB)"
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = ["-I", extractor.path, package.path, target.path]
        process.terminationHandler = { [weak self] finished in
            let ok = finished.terminationStatus == 0
            Task { @MainActor in
                guard let self else { return }
                self.extracting = false
                if ok && FileManager.default.fileExists(atPath: target.path + "/default.xex") {
                    self.gameFolder = target.path
                    self.extractStatus = "Extracted to \(target.path)"
                } else {
                    self.extractStatus = "Extraction failed: is this the package's header file (with its .data folder)?"
                }
            }
        }
        do { try process.run() } catch {
            extracting = false
            extractStatus = "Could not start python3: \(error.localizedDescription)"
        }
    }

    static func tail(of url: URL, lines: Int) -> String {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return "" }
        return text.split(separator: "\n", omittingEmptySubsequences: false).suffix(lines).joined(separator: "\n")
    }
}
