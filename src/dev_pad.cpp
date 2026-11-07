// Scripted controller input for unattended runs (a small version of MCLA's dev pad). Off unless
// fifa19_pad_script or fifa19_pad_pipe is set.
//
// A synthetic input device is added next to the real pads and feeds guest user 0 (merged with them, so a
// real controller keeps working). Commands come from a script file and/or a named pipe, one per line:
//
//   press <button> [150ms]     hold <button> <duration>     down <button>     up <button>
//   trigger lt|rt <0..1> [duration]     stick lx|ly|rx|ry <-1..1> [duration]
//   release                    wait <duration>              log <text>        quit
//   set <cvar> <value>          shot <name>   (the next presented frame to <fifa19_shot_dir>/<name>.ppm)
//
// Buttons: a b x y lb rb back start ls rs up down left right. Durations: 500ms, 2s, 1.5s.
// The pipe: `mkfifo pad; ./fifa19 --fifa19_pad_pipe=pad`, then `echo "press start" > pad`.
#include <sys/stat.h>

#include <filesystem>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>

#include <rex/cvar.h>
#include <rex/input/input_driver.h>
#include <rex/input/input_system.h>
#include <rex/logging.h>
#include <rex/runtime.h>
#include <rex/ui/virtual_key.h>

REXCVAR_DEFINE_STRING(fifa19_pad_script, "", "FIFA19",
                      "Development: a file of scripted controller commands to run after start-up");
REXCVAR_DEFINE_STRING(fifa19_pad_pipe, "", "FIFA19",
                      "Development: a named pipe to read controller commands from while the game runs");
REXCVAR_DEFINE_STRING(fifa19_shot_dir, "shots", "FIFA19",
                      "Development: where the dev pad's shot command writes pictures (relative: the working folder)");

namespace {

using namespace rex;
using namespace rex::input;

struct PadValues {
  uint16_t buttons = 0;
  uint8_t lt = 0, rt = 0;
  int16_t lx = 0, ly = 0, rx = 0, ry = 0;
};

std::mutex g_mutex;
PadValues g_pad;
std::atomic<uint32_t> g_polls{0};
bool g_enabled = false;

constexpr auto kScriptPadId = static_cast<rex::input::DeviceId>(0x46494641);  // "FIFA"

class ScriptPad final : public rex::input::InputDriver {
 public:
  ScriptPad() : InputDriver(nullptr, 2) {}
  X_STATUS Setup() override { return X_STATUS_SUCCESS; }

  void EnumerateDevices(std::vector<rex::input::DeviceInfo>& out) override {
    rex::input::DeviceInfo info;
    info.id = kScriptPadId;
    info.name = "ScriptPad";
    info.synthetic = true;
    out.push_back(info);
  }

  X_RESULT GetDeviceState(rex::input::DeviceId id, X_INPUT_STATE* out) override {
    if (id != kScriptPadId) return X_ERROR_DEVICE_NOT_CONNECTED;
    if (out) {
      std::lock_guard lock(g_mutex);
      std::memset(out, 0, sizeof(*out));
      // Merged states keep the highest packet number: this one stays above a real pad's and changes with
      // every poll, so the game always reads it.
      out->packet_number = 0x40000000u + g_polls++;
      out->gamepad.buttons = g_pad.buttons;
      out->gamepad.left_trigger = g_pad.lt;
      out->gamepad.right_trigger = g_pad.rt;
      out->gamepad.thumb_lx = g_pad.lx;
      out->gamepad.thumb_ly = g_pad.ly;
      out->gamepad.thumb_rx = g_pad.rx;
      out->gamepad.thumb_ry = g_pad.ry;
    }
    return X_ERROR_SUCCESS;
  }

  X_RESULT GetDeviceCapabilities(rex::input::DeviceId id, uint32_t, X_INPUT_CAPABILITIES* out) override {
    if (id != kScriptPadId) return X_ERROR_DEVICE_NOT_CONNECTED;
    if (out) {
      std::memset(out, 0, sizeof(*out));
      out->type = 0x01;      // XINPUT_DEVTYPE_GAMEPAD
      out->sub_type = 0x01;  // XINPUT_DEVSUBTYPE_GAMEPAD
      out->gamepad.buttons = 0xFFFF;
      out->gamepad.left_trigger = out->gamepad.right_trigger = 0xFF;
      out->gamepad.thumb_lx = out->gamepad.thumb_ly = 0x7FFF;
      out->gamepad.thumb_rx = out->gamepad.thumb_ry = 0x7FFF;
    }
    return X_ERROR_SUCCESS;
  }

  X_RESULT SetDeviceVibration(rex::input::DeviceId id, X_INPUT_VIBRATION*) override {
    return id == kScriptPadId ? X_ERROR_SUCCESS : X_ERROR_DEVICE_NOT_CONNECTED;
  }

  // Key events from button edges, as the SDL driver makes them (menus may read XamInputGetKeystrokeEx).
  X_RESULT GetDeviceKeystroke(rex::input::DeviceId id, uint32_t, X_INPUT_KEYSTROKE* out) override {
    using rex::ui::VirtualKey;
    if (id != kScriptPadId) return X_ERROR_DEVICE_NOT_CONNECTED;
    if (!out) return X_ERROR_BAD_ARGUMENTS;
    static constexpr VirtualKey kKeys[16] = {
        VirtualKey::kXInputPadDpadUp,      VirtualKey::kXInputPadDpadDown, VirtualKey::kXInputPadDpadLeft,
        VirtualKey::kXInputPadDpadRight,   VirtualKey::kXInputPadStart,    VirtualKey::kXInputPadBack,
        VirtualKey::kXInputPadLThumbPress, VirtualKey::kXInputPadRThumbPress,
        VirtualKey::kXInputPadLShoulder,   VirtualKey::kXInputPadRShoulder, VirtualKey::kNone,
        VirtualKey::kNone,                 VirtualKey::kXInputPadA,         VirtualKey::kXInputPadB,
        VirtualKey::kXInputPadX,           VirtualKey::kXInputPadY,
    };
    uint32_t keys;
    {
      std::lock_guard lock(g_mutex);
      keys = g_pad.buttons;
    }
    std::lock_guard lock(keys_mutex_);
    const uint32_t changed = keys ^ last_keys_;
    for (int pass = 0; pass < 2; pass++) {
      for (int i = 0; i < 16; i++) {
        const uint32_t bit = 1u << i;
        if (!(changed & bit) || kKeys[i] == VirtualKey::kNone) continue;
        const bool pressed = keys & bit;
        if (pass == 0 && pressed) continue;  // key-ups first
        out->virtual_key = uint16_t(kKeys[i]);
        out->unicode = 0;
        out->user_index = 0;
        out->hid_code = 0;
        out->flags = pressed ? X_INPUT_KEYSTROKE_KEYDOWN : X_INPUT_KEYSTROKE_KEYUP;
        last_keys_ ^= bit;
        return X_ERROR_SUCCESS;
      }
    }
    last_keys_ = keys;
    return X_ERROR_EMPTY;
  }

 private:
  std::mutex keys_mutex_;
  uint32_t last_keys_ = 0;
};

uint16_t ButtonBit(const std::string& name) {
  static const std::pair<const char*, uint16_t> kButtons[] = {
      {"up", 0x0001},    {"down", 0x0002}, {"left", 0x0004}, {"right", 0x0008}, {"start", 0x0010},
      {"back", 0x0020},  {"ls", 0x0040},   {"rs", 0x0080},   {"lb", 0x0100},    {"rb", 0x0200},
      {"a", 0x1000},     {"b", 0x2000},    {"x", 0x4000},    {"y", 0x8000},
  };
  for (const auto& [n, bit] : kButtons) {
    if (name == n) return bit;
  }
  return 0;
}

// "500ms", "2s", "1.5s"; an empty string gives `fallback`.
std::chrono::milliseconds Duration(const std::string& text, int fallback_ms) {
  if (text.empty()) return std::chrono::milliseconds(fallback_ms);
  const double value = std::strtod(text.c_str(), nullptr);
  const bool ms = text.size() > 2 && text.compare(text.size() - 2, 2, "ms") == 0;
  return std::chrono::milliseconds(int64_t(ms ? value : value * 1000.0));
}

void Sleep(std::chrono::milliseconds d) { std::this_thread::sleep_for(d); }

void SetAxis(const std::string& axis, double v) {
  v = std::fmax(-1.0, std::fmin(1.0, v));
  std::lock_guard lock(g_mutex);
  if (axis == "lt") g_pad.lt = uint8_t(std::lround(std::fmax(0.0, v) * 255));
  else if (axis == "rt") g_pad.rt = uint8_t(std::lround(std::fmax(0.0, v) * 255));
  else {
    const int16_t value = int16_t(std::lround(v * 32767));
    if (axis == "lx") g_pad.lx = value;
    else if (axis == "ly") g_pad.ly = value;
    else if (axis == "rx") g_pad.rx = value;
    else if (axis == "ry") g_pad.ry = value;
  }
}

void SetButton(uint16_t bit, bool down) {
  std::lock_guard lock(g_mutex);
  g_pad.buttons = down ? (g_pad.buttons | bit) : (g_pad.buttons & ~bit);
}

// Runs one command; false for an error (logged).
bool Execute(const std::string& line) {
  std::istringstream in(line);
  std::string cmd, a, b, c;
  in >> cmd >> a >> b >> c;
  if (cmd.empty() || cmd[0] == '#') return true;
  if (cmd == "press" || cmd == "hold" || cmd == "down" || cmd == "up") {
    const uint16_t bit = ButtonBit(a);
    if (!bit) {
      REXLOG_WARN("dev pad: unknown button '{}' in '{}'", a, line);
      return false;
    }
    if (cmd == "down" || cmd == "up") {
      SetButton(bit, cmd == "down");
      return true;
    }
    SetButton(bit, true);
    Sleep(Duration(b, cmd == "press" ? 150 : 1000));
    SetButton(bit, false);
    Sleep(std::chrono::milliseconds(100));
    return true;
  }
  if (cmd == "trigger" || cmd == "stick") {
    SetAxis(a, std::strtod(b.c_str(), nullptr));
    if (!c.empty()) {
      Sleep(Duration(c, 0));
      SetAxis(a, 0.0);
    }
    return true;
  }
  if (cmd == "release") {
    std::lock_guard lock(g_mutex);
    g_pad = {};
    return true;
  }
  if (cmd == "wait") {
    Sleep(Duration(a, 0));
    return true;
  }
  if (cmd == "log") {
    REXLOG_INFO("dev pad: {}", line.size() > 4 ? line.substr(4) : std::string());
    return true;
  }
  if (cmd == "set") {
    if (!rex::cvar::SetFlagByName(a, b)) {
      REXLOG_WARN("dev pad: cannot set cvar '{}' to '{}'", a, b);
      return false;
    }
    REXLOG_INFO("dev pad: {} = {}", a, b);
    return true;
  }
  if (cmd == "shot") {
    // The Metal presenter writes what it paints (game and overlays) to metal_present_capture, at most every
    // 2 s: set for one capture, then cleared. No screen recording permission or window focus needed.
    if (a.empty() || a.find('/') != std::string::npos) {
      REXLOG_WARN("dev pad: shot needs a plain name, not '{}'", a);
      return false;
    }
    const std::string dir = REXCVAR_GET(fifa19_shot_dir);
    std::error_code error;
    std::filesystem::create_directories(dir, error);
    const std::string path = (std::filesystem::path(dir) / (a + ".ppm")).string();
    rex::cvar::SetFlagByName("metal_present_capture", path);
    Sleep(std::chrono::milliseconds(2200));
    rex::cvar::SetFlagByName("metal_present_capture", "");
    REXLOG_INFO("dev pad: shot {}", path);
    return true;
  }
  if (cmd == "quit") {
    REXLOG_INFO("dev pad: quit");
    std::_Exit(0);
  }
  REXLOG_WARN("dev pad: unknown command '{}'", line);
  return false;
}

void RunScript(const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    REXLOG_ERROR("dev pad: cannot read {}", path);
    return;
  }
  REXLOG_INFO("dev pad: running {}", path);
  for (std::string line; std::getline(in, line);) {
    if (!Execute(line)) break;
  }
  REXLOG_INFO("dev pad: {} done", path);
}

// Reads the pipe forever; each writer's lines run in order, and the pipe is opened again after it closes.
void RunPipe(const std::string& path) {
  struct stat st {};
  if (stat(path.c_str(), &st) != 0) {
    if (mkfifo(path.c_str(), 0600) != 0) {
      REXLOG_ERROR("dev pad: cannot make the pipe {}", path);
      return;
    }
  }
  REXLOG_INFO("dev pad: reading commands from {}", path);
  for (;;) {
    std::ifstream in(path);
    for (std::string line; std::getline(in, line);) {
      REXLOG_INFO("dev pad: > {}", line);
      Execute(line);
    }
  }
}

}  // namespace

// From Fifa19App::OnPreSetup: adds the synthetic pad when a pad option is set.
void Fifa19DevPadConfigure(rex::RuntimeConfig& config) {
  g_enabled = !REXCVAR_GET(fifa19_pad_script).empty() || !REXCVAR_GET(fifa19_pad_pipe).empty();
  if (!g_enabled) return;
  auto inner = config.input_factory;
  config.input_factory = [inner](bool tool_mode) -> std::unique_ptr<rex::system::IInputSystem> {
    auto system = inner ? inner(tool_mode) : nullptr;
    if (system && !tool_mode) {
      static_cast<rex::input::InputSystem*>(system.get())->AddDriver(std::make_unique<ScriptPad>());
    }
    return system;
  };
}

// From Fifa19App::OnPostSetup: starts reading commands.
void Fifa19DevPadStart() {
  if (!g_enabled) return;
  const std::string script = REXCVAR_GET(fifa19_pad_script), pipe = REXCVAR_GET(fifa19_pad_pipe);
  if (!script.empty()) std::thread(RunScript, script).detach();
  if (!pipe.empty()) std::thread(RunPipe, pipe).detach();
}
