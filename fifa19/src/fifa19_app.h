// fifa19 - ReXGlue recompiled FIFA 19 (Xbox 360) for macOS

#pragma once

#include <memory>

#include <rex/rex_app.h>
#include <rex/ui/window.h>

// Defined by codegen in generated/default/fifa19_init.cpp.
extern const rex::PPCImageInfo PPCImageConfig;

class Fifa19App : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<Fifa19App>(new Fifa19App(ctx, "fifa19", PPCImageConfig));
  }

 protected:
  void OnPreSetup(rex::RuntimeConfig& config) override;
  void OnConfigurePaths(rex::PathConfig& paths) override;
  void OnPostSetup() override;
  void OnCreateDialogs(rex::ui::ImGuiDrawer* drawer) override;
};
