// The game's settings the launcher offers: each a cvar in fifa19.toml with the game's own default (a setting
// left at its default is no line in the file). They apply at the next start of the game.

import SwiftUI

struct Setting: Identifiable {
    enum Kind {
        case toggle
        case choice([(value: String, label: String)])
        case numberChoice([(value: Double, label: String)])
        case number(range: ClosedRange<Int>)
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
                detail: "Less shimmer on lines and edges; the picture is softer (the grass's fine texture is smoothed).",
                kind: .toggle, defaultValue: .bool(false)),
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
    ]
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
            }
            if !s.detail.isEmpty { Text(s.detail).font(.caption).foregroundStyle(.secondary) }
        }
    }
}
