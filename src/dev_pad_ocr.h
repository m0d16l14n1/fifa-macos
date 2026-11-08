// Text on a captured frame, for the dev pad (dev_pad_ocr.mm, macOS Vision).
#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct DevPadTextLine {
  std::string text;
  float x = 0, y = 0, w = 0, h = 0;  // in 0..1 of the frame, origin at the top left
  uint8_t rgb[3] = {};               // the mean colour of the box
};

struct DevPadFrame {
  uint32_t width = 0, height = 0;
  std::vector<uint8_t> rgb;
  std::vector<DevPadTextLine> lines;
};

// Reads a binary PPM and the text on it; false if the file can't be read or recognition fails.
bool DevPadReadText(const std::string& ppm_path, DevPadFrame& frame);
