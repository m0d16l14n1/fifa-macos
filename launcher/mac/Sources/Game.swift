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

    func play() {
        guard running == nil, programInstalled else { return }
        let process = Process()
        process.executableURL = paths.program
        process.currentDirectoryURL = paths.logs  // stall reports land next to the log
        var arguments = ["--log_file=\(paths.log.path)"]
        if gameInstalled { arguments.append("--game_data_root=\(gameFolder)") }
        arguments += extraArguments.split(separator: " ").map(String.init)
        process.arguments = arguments
        var env = ProcessInfo.processInfo.environment
        if metalHud { env["MTL_HUD_ENABLED"] = "1" }
        if metalValidation { env["MTL_DEBUG_LAYER"] = "1"; env["METAL_DEVICE_WRAPPER_TYPE"] = "1" }
        if backgroundWindow { env["SDL_MAC_BACKGROUND_APP"] = "1"; env["SDL_WINDOW_ACTIVATE_WHEN_SHOWN"] = "0" }
        process.environment = env
        process.terminationHandler = { [weak self] finished in
            let status = finished.terminationStatus, reason = finished.terminationReason
            Task { @MainActor in
                guard let self else { return }
                self.running = nil
                self.reload()
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
