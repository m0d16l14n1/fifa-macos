// The dev pad's eyes: the text on a captured frame (a binary PPM from the Metal presenter), read with Vision's text
// recognizer, each line with its box and the mean colour behind it, so a script can wait for a screen and see
// which menu item is highlighted.
#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>
#import <Vision/Vision.h>

#include <cstdio>
#include <string>
#include <vector>

#include "dev_pad_ocr.h"

namespace {

bool ReadPpm(const std::string& path, uint32_t& width, uint32_t& height, std::vector<uint8_t>& rgb) {
  FILE* file = std::fopen(path.c_str(), "rb");
  if (!file) return false;
  unsigned w = 0, h = 0, max = 0;
  const bool ok = std::fscanf(file, "P6 %u %u %u", &w, &h, &max) == 3 && max == 255 && w && h;
  if (ok) {
    std::fgetc(file);  // the one whitespace byte after the header
    rgb.resize(size_t(w) * h * 3);
    width = w;
    height = h;
  }
  const bool read = ok && std::fread(rgb.data(), 1, rgb.size(), file) == rgb.size();
  std::fclose(file);
  return read;
}

}  // namespace

bool DevPadReadText(const std::string& ppm_path, DevPadFrame& frame) {
  frame = {};
  if (!ReadPpm(ppm_path, frame.width, frame.height, frame.rgb)) return false;
  @autoreleasepool {
    CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
    CFDataRef data = CFDataCreate(nullptr, frame.rgb.data(), CFIndex(frame.rgb.size()));
    CGDataProviderRef provider = CGDataProviderCreateWithCFData(data);
    CGImageRef image = CGImageCreate(frame.width, frame.height, 8, 24, frame.width * 3, space,
                                     kCGBitmapByteOrderDefault | kCGImageAlphaNone, provider, nullptr, false,
                                     kCGRenderingIntentDefault);
    CGDataProviderRelease(provider);
    CFRelease(data);
    CGColorSpaceRelease(space);
    if (!image) return false;
    VNRecognizeTextRequest* request = [[VNRecognizeTextRequest alloc] init];
    request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
    request.usesLanguageCorrection = NO;  // team and stadium names, times, menu words in capitals
    VNImageRequestHandler* handler = [[VNImageRequestHandler alloc] initWithCGImage:image options:@{}];
    NSError* error = nil;
    const bool performed = [handler performRequests:@[ request ] error:&error];
    CGImageRelease(image);
    if (!performed) return false;
    for (VNRecognizedTextObservation* observation in request.results) {
      VNRecognizedText* best = [observation topCandidates:1].firstObject;
      if (!best) continue;
      DevPadTextLine line;
      line.text = best.string.UTF8String;
      // Vision's boxes are normalized with the origin at the bottom left.
      const CGRect box = observation.boundingBox;
      line.x = float(box.origin.x);
      line.y = float(1.0 - box.origin.y - box.size.height);
      line.w = float(box.size.width);
      line.h = float(box.size.height);
      // The mean colour of the box: a highlighted menu item sits on a coloured bar.
      const uint32_t x0 = uint32_t(line.x * frame.width), x1 = uint32_t((line.x + line.w) * frame.width);
      const uint32_t y0 = uint32_t(line.y * frame.height), y1 = uint32_t((line.y + line.h) * frame.height);
      uint64_t sum[3] = {}, count = 0;
      for (uint32_t y = y0; y < y1 && y < frame.height; ++y) {
        for (uint32_t x = x0; x < x1 && x < frame.width; ++x) {
          const uint8_t* p = &frame.rgb[(size_t(y) * frame.width + x) * 3];
          sum[0] += p[0]; sum[1] += p[1]; sum[2] += p[2];
          ++count;
        }
      }
      for (int c = 0; c < 3; ++c) line.rgb[c] = count ? uint8_t(sum[c] / count) : 0;
      frame.lines.push_back(line);
    }
  }
  return true;
}
