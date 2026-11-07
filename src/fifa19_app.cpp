// fifa19 - ReXGlue recompiled FIFA 19 (Xbox 360) for macOS

#include "fifa19_app.h"

#include <cstdlib>
#include <filesystem>
#include <string>
#include <utility>

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/filesystem/devices/host_path_device.h>
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <rex/runtime.h>
#include <rex/system/gpu_plugin.h>

void Fifa19DevPadConfigure(rex::RuntimeConfig& config);  // dev_pad.cpp
void Fifa19BeginGameActivity();                          // mac_activity.mm
void Fifa19DevPadStart();

// Metal is the default on macOS: the SDK's native Xenos backend (MCLA's rexglue-metal-backend.patch).
// "vulkan" runs through MoltenVK for comparison; "any" lets the plugin choose.
REXCVAR_DEFINE_STRING(fifa19_gpu_backend, "metal", "FIFA19",
                      "Graphics API of the xenos GPU plugin: metal, vulkan or any")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

// Unattended test runs name their window, so a player can tell them from a game they started.
REXCVAR_DEFINE_STRING(fifa19_window_title, "FIFA 19", "FIFA19", "The window's title")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_BOOL(fifa19_temporal_aa, false, "FIFA19",
                    "MetalFX temporal anti-aliasing of the 3D scene (less shimmer on lines and edges, a softer "
                    "picture: the grass's fine texture is smoothed). Restart")
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

// Defaults for the Metal backend's cvars, which exist once the GPU plugin is loaded and are read when the GPU
// starts (before OnPostSetup). Defaults only: fifa19.toml and the command line still change them.
static void SetMetalDefaults() {
  static constexpr std::pair<const char*, const char*> kDefaults[] = {
      // The pitch's shadow textures are made at match load by the CPU from GPU resolves, read once the guest's
      // fence is written: fences the command processor wrote at once (before the GPU had done the resolves) gave
      // stale bytes, so dark bands or a black pitch.
      {"metal_gpu_fences", "true"},
      // The game draws 1280x720: MetalFX's spatial upscaler is sharper than bilinear on a larger window.
      {"metal_present_upscale", "metalfx"},
      // A stall of 2 s leaves every thread's stack in stall-<time>.txt in the working folder.
      {"metal_stall_sample_ms", "2000"},
      // Smooth: the guest vblank on each refresh of the display, so every refresh shows the next game frame (a
      // match on a 60 Hz screen: 60.1 frames shown a second, none repeated or dropped, each 16.7 ms of game time
      // +-0.7 ms). Paced by its own 240 Hz clock the game made ~80 frames a second at uneven times and each
      // refresh showed the newest: motion stepped 12 to 24 ms a refresh, which shows as judder on the crowd.
      // false: video_mode_refresh_rate's clock (uncapped at 240).
      {"gpu_vblank_display_sync", "true"},
      // Temporal AA's place in FIFA's frame (temporal_aa_anchor_ps, temporal_aa_camera; on with
      // fifa19_temporal_aa): the pass runs before the composite that first reads the scene (pixel shader
      // C4F1B7FC, texture 0 the 1280x720 scene; the depth is the frame's last depth resolve), and the camera is
      // the view-projection in the scene's vertex shaders' constants: the players' (443F0A79: c1-c4 after
      // skinning to world space; F4EC1B9B, 6798832A: c1-c4) and the skinned props' (EC79FAF2, 71347B6C:
      // c0-c3 after their world matrix in c32-c35). Found in a match frame dump (docs/METAL.md).
      {"temporal_aa_anchor_ps", "C4F1B7FC4C922703"},
      {"temporal_aa_camera",
       "443F0A79A4511E2A:1,EC79FAF2D2D5D3A2:0,71347B6C3E6EF3F3:0,F4EC1B9B71624CC5:1,6798832ABD1C5D32:1"},
  };
  for (const auto& [name, value] : kDefaults) {
    if (!rex::cvar::SetDefaultValue(name, value)) {
      REXLOG_WARN("fifa19: no GPU default for {} (another GPU backend?)", name);
    }
  }
}

void Fifa19App::OnPreSetup(rex::RuntimeConfig& config) {
  Fifa19BeginGameActivity();
  SetKeyboardDefaults();
  // A window by default (the SDK starts fullscreen); fullscreen=true in fifa19.toml or on the command line.
  rex::cvar::SetDefaultValue("fullscreen", "false");
  // The guest vblank's own clock when it isn't synced to the display (gpu_vblank_display_sync=false, below): 240 Hz
  // instead of the console's 60, so frames come as fast as the game makes them (about 80 a second in a match on an
  // M5). FIFA's simulation is time-based: the match clock runs at the same rate as at 60 Hz (measured).
  // vsync=false (the vblank every millisecond) is faster still but uneven.
  rex::cvar::SetDefaultValue("video_mode_refresh_rate", "240");
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
  SetMetalDefaults();
}

REXCVAR_DECLARE(std::string, user_data_root);
REXCVAR_DECLARE(std::string, cache_root);

namespace {

// ~/Library/Application Support/FIFA 19: the profile and saves, the shader caches and fifa19.toml.
std::filesystem::path SupportFolder() {
  const char* home = std::getenv("HOME");
  return std::filesystem::path(home ? home : ".") / "Library" / "Application Support" / "FIFA 19";
}

// Builds before this one kept the profile in the SDK's XDG folder (~/.local/share/fifa19): moved once.
void MigrateOldUserFolder(const std::filesystem::path& support) {
  const char* home = std::getenv("HOME");
  if (!home) return;
  const auto old = std::filesystem::path(home) / ".local" / "share" / "fifa19";
  std::error_code error;
  if (std::filesystem::exists(support, error) || !std::filesystem::is_directory(old, error)) return;
  std::filesystem::create_directories(support.parent_path(), error);
  std::filesystem::rename(old, support, error);
  if (error) {
    REXLOG_WARN("fifa19: could not move {} to {}: {}", old.string(), support.string(), error.message());
  }
}

}  // namespace

void Fifa19App::OnConfigurePaths(rex::PathConfig& paths) {
  // User data, caches and settings in the Mac's own place, unless set on the command line. A fifa19.toml next
  // to the program (a development build tree) still wins over the one in the support folder.
  const auto support = SupportFolder();
  if (REXCVAR_GET(user_data_root).empty()) {
    MigrateOldUserFolder(support);
    paths.user_data_root = support;
    if (REXCVAR_GET(cache_root).empty()) paths.cache_root = support / "cache";
  }
  std::error_code exists_error;
  if (!std::filesystem::exists(paths.config_path, exists_error)) {
    paths.config_path = support / "fifa19.toml";
  }
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

// The console's cache partition (cache:\), which the SDK leaves unmounted: FIFA keeps replay0.bin there (instant
// replays and highlights). A writable folder in the user data.
static void MountCacheDevice() {
  auto* runtime = rex::Runtime::instance();
  auto* vfs = runtime ? runtime->file_system() : nullptr;
  if (!vfs || runtime->user_data_root().empty()) return;
  const auto root = runtime->user_data_root() / "cache-partition";
  std::error_code error;
  std::filesystem::create_directories(root, error);
  constexpr const char* kMountPath = "\\Device\\FifaCache";
  auto device = std::make_unique<rex::filesystem::HostPathDevice>(kMountPath, root, /*read_only=*/false);
  if (error || !device->Initialize() || !vfs->RegisterDevice(std::move(device)) ||
      !vfs->RegisterSymbolicLink("cache:", kMountPath)) {
    REXLOG_WARN("fifa19: cache:\\ could not be mounted on {}", root.string());
    return;
  }
  REXLOG_INFO("fifa19: cache:\\ is {}", root.string());
}

void Fifa19App::OnPostSetup() {
  MountCacheDevice();
  // EA's engine (as in FIFA Street) leaves texture fetch constants tagged invalid whose address and
  // format fields are still in use.
  rex::cvar::SetFlagByName("gpu_allow_invalid_fetch_constants", "true");
  // temporal_aa is a title's runtime switch (not read from a config file): FIFA's own setting sets it.
  if (REXCVAR_GET(fifa19_temporal_aa)) rex::cvar::SetFlagByName("temporal_aa", "fsr");
  Fifa19DevPadStart();
}

void Fifa19App::OnCreateDialogs(rex::ui::ImGuiDrawer*) {
  window()->SetTitle(REXCVAR_GET(fifa19_window_title));
}
