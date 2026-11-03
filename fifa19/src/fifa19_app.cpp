// fifa19 - ReXGlue recompiled FIFA 19 (Xbox 360) for macOS

#include "fifa19_app.h"

#include <filesystem>
#include <string>
#include <utility>

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/logging.h>
#include <rex/runtime.h>
#include <rex/system/gpu_plugin.h>

void Fifa19DevPadConfigure(rex::RuntimeConfig& config);  // dev_pad.cpp
void Fifa19DevPadStart();

// Metal is the default on macOS: the SDK's native Xenos backend (MCLA's rexglue-metal-backend.patch).
// "vulkan" runs through MoltenVK for comparison; "any" lets the plugin choose.
REXCVAR_DEFINE_STRING(fifa19_gpu_backend, "metal", "FIFA19",
                      "Graphics API of the xenos GPU plugin: metal, vulkan or any")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

// Unattended test runs name their window, so a player can tell them from a game they started.
REXCVAR_DEFINE_STRING(fifa19_window_title, "FIFA 19", "FIFA19", "The window's title")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

// The keyboard plays as pad one (merged with any real pad), laid out like FIFA's keyboard-only Classic controls on
// PC: arrows move, W/A/S/D are through ball / lob / pass / shoot. These are defaults: the config file, the command
// line and the settings overlay (F4) still change them. README.md lists them all.
static void SetKeyboardDefaults() {
  static constexpr std::pair<const char*, const char*> kDefaults[] = {
      {"mnk_mode", "true"},
      {"keybind_lstick_up", "Up"},
      {"keybind_lstick_down", "Down"},
      {"keybind_lstick_left", "Left"},
      {"keybind_lstick_right", "Right"},
      {"keybind_a", "S,Return"},       // short pass, tackle, menu accept
      {"keybind_b", "D,Backspace"},    // shoot, push or pull, menu back
      {"keybind_x", "A"},              // lob pass / cross, slide tackle
      {"keybind_y", "W"},              // through ball, goalkeeper rush
      {"keybind_left_shoulder", "Q"},  // change player, player run, chip / lobbed modifier
      {"keybind_right_shoulder", "C"}, // finesse modifier, teammate contain
      {"keybind_left_trigger", "Z"},   // protect ball, jockey, slow dribble
      {"keybind_right_trigger", "E"},  // sprint
      {"keybind_lstick_press", "F"},
      {"keybind_rstick_press", "T"},   // flick up for volley, cover far post
      {"keybind_rstick_up", "Numpad8,I"},  // skill moves
      {"keybind_rstick_down", "Numpad2,K"},
      {"keybind_rstick_left", "Numpad4,J"},
      {"keybind_rstick_right", "Numpad6,L"},
      {"keybind_dpad_up", "Shift+Up"},  // tactics
      {"keybind_dpad_down", "Shift+Down"},
      {"keybind_dpad_left", "Shift+Left"},
      {"keybind_dpad_right", "Shift+Right"},
      {"keybind_start", "Escape,Space"},  // pause, and "Press START" on the title screen
      {"keybind_back", "Tab"},
  };
  for (const auto& [name, value] : kDefaults) {
    if (!rex::cvar::SetDefaultValue(name, value)) {
      REXLOG_WARN("fifa19: no keyboard default for {}", name);
    }
  }
}

void Fifa19App::OnPreSetup(rex::RuntimeConfig& config) {
  SetKeyboardDefaults();
  if (config.gpu_plugin.empty()) {
    config.gpu_plugin = "xenos";
  }
  Fifa19DevPadConfigure(config);
  const std::string backend = REXCVAR_GET(fifa19_gpu_backend);
  if (!config.graphics && backend != "any") {
    config.graphics = rex::system::LoadGpuPlugin(config.gpu_plugin, backend);
    if (!config.graphics) {
      REXLOG_ERROR("fifa19: the xenos plugin has no '{}' backend; using its default", backend);
    }
  }
}

void Fifa19App::OnConfigurePaths(rex::PathConfig& paths) {
  if (!paths.game_data_root.empty()) {
    return;
  }
  // The extracted disc: next to the executable, or the project's game/ folder when run from the build tree
  // (out/build/<preset>/fifa19) or from an app bundle (FIFA19.app/Contents/MacOS/fifa19).
  const auto exe = rex::filesystem::GetExecutableFolder();
  for (const auto& candidate : {exe / "game", exe.parent_path() / "Resources" / "game",
                                exe / ".." / ".." / ".." / "game", exe}) {
    std::error_code error;
    if (std::filesystem::is_regular_file(candidate / "default.xex", error)) {
      paths.game_data_root = std::filesystem::weakly_canonical(candidate, error);
      return;
    }
  }
}

void Fifa19App::OnPostSetup() {
  // EA's engine (as in FIFA Street) leaves texture fetch constants tagged invalid whose address and
  // format fields are still in use.
  rex::cvar::SetFlagByName("gpu_allow_invalid_fetch_constants", "true");
  // The pitch's shadow textures are made at match load by the CPU from GPU resolves, read once the guest's fence
  // is written: fences the command processor wrote at once (before the GPU had done the resolves) gave stale
  // bytes, so dark bands or a black pitch. The GPU writes them after the work before them.
  rex::cvar::SetDefaultValue("metal_gpu_fences", "true");
  // The game draws 1280x720: MetalFX's spatial upscaler is sharper than bilinear on a larger window.
  rex::cvar::SetDefaultValue("metal_present_upscale", "metalfx");
  // A stall of 2 s leaves every thread's stack in stall-<time>.txt next to the log.
  rex::cvar::SetDefaultValue("metal_stall_sample_ms", "2000");
  Fifa19DevPadStart();
}

void Fifa19App::OnCreateDialogs(rex::ui::ImGuiDrawer*) {
  window()->SetTitle(REXCVAR_GET(fifa19_window_title));
}
