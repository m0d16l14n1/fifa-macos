# fifa19 - ReXGlue recompiled FIFA 19 (Xbox 360) for macOS
#
# SDK boilerplate lives in generated/rexglue.cmake (written by `rexglue codegen`).

cmake_minimum_required(VERSION 3.25)
project(fifa19 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(generated/rexglue.cmake)

set(FIFA19_SOURCES
    src/main.cpp
    src/fifa19_app.cpp
    src/stubs.cpp
    src/native_libc_hooks.cpp
    src/native_frame_limiter.cpp
    src/mac_activity.mm
    src/dev_pad.cpp
)

add_executable(fifa19 ${FIFA19_SOURCES})

rexglue_setup_target(fifa19 GPU_PLUGINS xenos)
target_include_directories(fifa19 PRIVATE src)

# Objective-C++ (ARC) for the macOS pieces, compiled by the C++ compiler.
set_source_files_properties(src/mac_activity.mm PROPERTIES LANGUAGE CXX COMPILE_OPTIONS "-xobjective-c++;-fobjc-arc")
target_link_libraries(fifa19 PRIVATE "-framework Foundation")

# The SDK keeps ImGui private to rexruntime; its public UI headers still need the include directory.
if(TARGET imgui::imgui)
    target_include_directories(fifa19 PRIVATE
        $<TARGET_PROPERTY:imgui::imgui,INTERFACE_INCLUDE_DIRECTORIES>)
endif()

# Guest SIMD code must be optimized even in debug builds (ReStreet does the same).
foreach(t fifa19 fifa19_recomp fifa19_CardsDLLzf_xex fifa19_FootballCompEngzf_xex fifa19_powdllzf_xex)
    if(TARGET ${t})
        target_compile_options(${t} PRIVATE -O2)
    endif()
endforeach()

