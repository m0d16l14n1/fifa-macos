// The game's settings the launcher offers: each a cvar in fifa19.toml with the game's own default (a setting
// left at its default is no line in the file). They apply at the next start of the game.

import SwiftUI

struct Setting: Identifiable {
    enum Kind {
        case toggle
        case choice([(value: String, label: String)])
        case numberChoice([(value: Double, label: String)])
        case number(range: ClosedRange<Int>)
        case text  // free text, applied when edited (a key binding: comma-separated SDL key names)
    }

    let key: String
    let title: String
    let detail: String
    let kind: Kind
    let defaultValue: TomlValue
    var id: String { key }

    static let graphics: [Setting] = [
        Setting(key: "fifa19_gpu_backend", title: "Renderer",
                detail: "Metal is native. Vulkan runs through MoltenVK, for comparison.",
                kind: .choice([("metal", "Metal"), ("vulkan", "Vulkan (MoltenVK)")]), defaultValue: .string("metal")),
        Setting(key: "metal_present_upscale", title: "Upscaling to the window",
                detail: "The game draws 1280x720. MetalFX's spatial upscaler is sharper than bilinear.",
                kind: .choice([("metalfx", "MetalFX spatial"), ("bilinear", "Bilinear")]), defaultValue: .string("metalfx")),
        Setting(key: "fullscreen", title: "Fullscreen", detail: "Off: a window (it can be resized).",
                kind: .toggle, defaultValue: .bool(false)),
        Setting(key: "gpu_vblank_display_sync", title: "Sync to the display",
                detail: "Smoothest: one new frame every refresh of the screen (60 FPS on a 60 Hz display). "
                    + "Off: the frame rate below, faster but less even.",
                kind: .toggle, defaultValue: .bool(true)),
        Setting(key: "video_mode_refresh_rate", title: "Frame rate when not synced",
                detail: "The game paces its frames by this clock. 240: uncapped (as fast as the Mac draws them). "
                    + "60: as on the console.",
                kind: .numberChoice([(240, "Uncapped (up to 240)"), (120, "Up to 120"), (60, "60, as on the console")]),
                defaultValue: .double(240)),
        Setting(key: "vsync", title: "Pace frames by that clock",
                detail: "Off: no pacing at all; faster still, but frames come at uneven times (choppy).",
                kind: .toggle, defaultValue: .bool(true)),
        Setting(key: "fifa19_temporal_aa", title: "Temporal anti-aliasing (MetalFX)",
                detail: "Less shimmer on lines and edges, sharpened after it. No measurable cost in FPS.",
                kind: .toggle, defaultValue: .bool(true)),
        Setting(key: "frame_generation", title: "Frame generation (MetalFX)",
                detail: "A frame generated between every two when the game runs below the display's rate: "
                    + "cut-scenes and replays (30 FPS) at 60. Turns temporal anti-aliasing on. macOS 26.",
                kind: .choice([("off", "Off"), ("fsr", "On")]), defaultValue: .string("off")),
        Setting(key: "metal_gpu_fences", title: "GPU fences",
                detail: "Needed for the pitch's shadows (they are baked from GPU work at match load).",
                kind: .toggle, defaultValue: .bool(true)),
        Setting(key: "metal_resolve_into_textures", title: "Resolves into loaded textures",
                detail: "Copies the game's GPU copies into textures already loaded instead of reloading them (much faster in matches).",
                kind: .toggle, defaultValue: .bool(true)),
        Setting(key: "metal_hitch_log_ms", title: "Log frames slower than (ms)",
                detail: "A 'Metal hitch' line in the log for each; 0 turns it off.",
                kind: .number(range: 0...5000), defaultValue: .int(250)),
    ]

    static let controls: [Setting] = [
        Setting(key: "mnk_mode", title: "Keyboard as a controller",
                detail: "Plays as pad one with any controller; FIFA's keyboard-only Classic layout (README, Controls). "
                    + "F4 in the game changes the keys.",
                kind: .toggle, defaultValue: .bool(true)),
        Setting(key: "mnk_mouse", title: "Mouse as the right stick", detail: "Skill moves with the mouse.",
                kind: .toggle, defaultValue: .bool(false)),
        Setting(key: "audio_mute", title: "Mute audio", detail: "", kind: .toggle, defaultValue: .bool(false)),
    ] + keys

    // The keyboard as pad one (FIFA's keyboard-only Classic layout by default, Fifa19App's SetKeyboardDefaults):
    // each pad control's keys, comma-separated SDL key names (Return, Backspace, Shift+Up, Numpad8...).
    static let keys: [Setting] = [
        ("keybind_a", "A: short pass, tackle, menu accept", "S,Return"),
        ("keybind_b", "B: shoot, push or pull, menu back", "D,Backspace"),
        ("keybind_x", "X: lob pass, cross, slide tackle", "A"),
        ("keybind_y", "Y: through ball, goalkeeper rush", "W"),
        ("keybind_left_shoulder", "LB: change player, player run", "Q"),
        ("keybind_right_shoulder", "RB: finesse, teammate contain", "C"),
        ("keybind_left_trigger", "LT: protect the ball, jockey", "Z"),
        ("keybind_right_trigger", "RT: sprint", "E"),
        ("keybind_lstick_up", "Move up", "Up"),
        ("keybind_lstick_down", "Move down", "Down"),
        ("keybind_lstick_left", "Move left", "Left"),
        ("keybind_lstick_right", "Move right", "Right"),
        ("keybind_lstick_press", "Left stick press", "F"),
        ("keybind_rstick_press", "Right stick press: flick up for a volley", "T"),
        ("keybind_rstick_up", "Skill moves: up", "Numpad8,I"),
        ("keybind_rstick_down", "Skill moves: down", "Numpad2,K"),
        ("keybind_rstick_left", "Skill moves: left", "Numpad4,J"),
        ("keybind_rstick_right", "Skill moves: right", "Numpad6,L"),
        ("keybind_dpad_up", "Tactics: up", "Shift+Up"),
        ("keybind_dpad_down", "Tactics: down", "Shift+Down"),
        ("keybind_dpad_left", "Tactics: left", "Shift+Left"),
        ("keybind_dpad_right", "Tactics: right", "Shift+Right"),
        ("keybind_start", "Start: pause", "Escape,Space"),
        ("keybind_back", "Back", "Tab"),
    ].map { Setting(key: $0.0, title: $0.1, detail: "", kind: .text, defaultValue: .string($0.2)) }
}

struct SettingsPage: View {
    @EnvironmentObject var game: Game
    let title: String
    let settings: [Setting]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title).font(.title.bold())
            Text("Applied at the next start of the game.").foregroundStyle(.secondary)
            Form {
                ForEach(settings) { setting in
                    row(setting)
                }
            }
            .formStyle(.grouped)
        }
    }

    @ViewBuilder
    private func row(_ s: Setting) -> some View {
        let current = game.value(s.key) ?? s.defaultValue
        VStack(alignment: .leading, spacing: 2) {
            switch s.kind {
            case .toggle:
                Toggle(s.title, isOn: Binding(get: { current.bool ?? false },
                                              set: { game.set(s.key, .bool($0), default: s.defaultValue) }))
            case .choice(let options):
                Picker(s.title, selection: Binding(get: { current.string ?? "" },
                                                   set: { game.set(s.key, .string($0), default: s.defaultValue) })) {
                    ForEach(options, id: \.value) { Text($0.label).tag($0.value) }
                }
            case .numberChoice(let options):
                Picker(s.title, selection: Binding(get: { current.number ?? 0 },
                                                   set: { game.set(s.key, .double($0), default: s.defaultValue) })) {
                    ForEach(options, id: \.value) { Text($0.label).tag($0.value) }
                }
            case .number(let range):
                Stepper(value: Binding(get: { current.int ?? range.lowerBound },
                                       set: { game.set(s.key, .int($0), default: s.defaultValue) }),
                        in: range, step: 50) {
                    Text("\(s.title): \(current.int ?? range.lowerBound)")
                }
            case .text:
                KeyField(title: s.title, value: current.string ?? "") { text in
                    let trimmed = text.trimmingCharacters(in: .whitespaces)
                    game.set(s.key, trimmed.isEmpty ? nil : .string(trimmed), default: s.defaultValue)
                }
            }
            if !s.detail.isEmpty { Text(s.detail).font(.caption).foregroundStyle(.secondary) }
        }
    }
}

// A text setting that is written when editing ends (return or leaving the field), not on every keystroke.
private struct KeyField: View {
    let title: String
    let value: String
    let commit: (String) -> Void
    @State private var text = ""
    @FocusState private var focused: Bool

    var body: some View {
        TextField(title, text: $text)
            .focused($focused)
            .onAppear { text = value }
            .onChange(of: value) { _, new in if !focused { text = new } }
            .onSubmit { commit(text) }
            .onChange(of: focused) { _, now in if !now { commit(text) } }
    }
}
