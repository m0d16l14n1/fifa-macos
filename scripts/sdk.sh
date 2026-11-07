#!/usr/bin/env bash
# Builds the ReXGlue SDK FIFA 19 runs on: upstream v0.10.0, the mcla-recomp patch series at ef468c4
# (patches/mcla/series, the Metal backend among them), then FIFA 19's own (patches/fifa/*.patch).
#
#   bash scripts/sdk.sh [--config RelWithDebInfo|Release|Debug] [--jobs N] [--check]
#
# The checkout is third_party/rexglue-sdk (gitignored), built in its out/build/mac-arm64 and installed in its
# out/install/mac-arm64. Each step is skipped when its result is there, so the script can be run again.
# Every applied patch is recorded with its hash in third_party/rexglue-sdk/.fifa-patches; a patch that has changed
# since is reported (delete third_party/rexglue-sdk and run again to patch afresh).
#   --check   only verify that the checkout matches the patches (no build)
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/third_party/rexglue-sdk"
build="$src/out/build/mac-arm64"
records="$src/.fifa-patches"
tag=v0.10.0
commit=f5337cdc947ff6d4c4196737e2c807a48f2a1fc2
config=RelWithDebInfo jobs=$(sysctl -n hw.ncpu) check_only=

while [ $# -gt 0 ]; do
  case $1 in
    --config) config=$2; shift 2 ;;
    --jobs) jobs=$2; shift 2 ;;
    --check) check_only=1; shift ;;
    -h|--help) sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done
case $config in Debug|RelWithDebInfo|Release) ;; *) echo "--config: Debug, RelWithDebInfo or Release" >&2; exit 2 ;; esac

fail() { printf 'sdk.sh: %s\n' "$*" >&2; exit 1; }
logs="$repo/out/logs"; mkdir -p "$logs"
logged() {
  local name=$1; shift
  if ! "$@" > "$logs/$name.log" 2>&1; then
    tail -25 "$logs/$name.log" >&2
    fail "$name failed (full log: $logs/$name.log)"
  fi
}
hash_of() { shasum -a 256 < "$1" | cut -d' ' -f1; }

# The patches in order: "<file> [submodule dir]" lines.
patch_list() {
  grep -v '^#' "$repo/patches/mcla/series" | sed '/^$/d' | sed 's|^|mcla/|'
  for p in "$repo"/patches/fifa/*.patch; do echo "fifa/$(basename "$p")"; done
}

if [ ! -d "$src/.git" ]; then
  [ -n "$check_only" ] && fail "no SDK checkout at $src"
  echo "==> cloning ReXGlue $tag"
  logged sdk-clone git clone --recursive --depth 1 --shallow-submodules --branch "$tag" \
    https://github.com/rexglue/rexglue-sdk.git "$src"
fi

if [ ! -f "$records" ]; then
  [ -n "$check_only" ] && fail "the checkout has no patch records ($records)"
  [ "$(git -C "$src" rev-parse HEAD)" = "$commit" ] || fail "the checkout is not $tag ($commit)"
  echo "==> applying $(patch_list | wc -l | tr -d ' ') patches"
  # The MCLA series as one commit tagged mcla-base, then FIFA's patches as commits of their own (branch fifa):
  # `git format-patch mcla-base..fifa` exports them again after a change; a new last commit alone:
  # `git format-patch -1 fifa --start-number <n>`.
  ident=(-c user.name=fifa19-macos -c user.email=fifa19-macos@localhost)
  git -C "$src" checkout -q -B fifa
  : > "$records.partial"
  while read -r patch dir; do
    case $patch in
      mcla/*)
        if [ -n "$dir" ]; then
          git -C "$src/$dir" apply --whitespace=nowarn "$repo/patches/$patch" || fail "$patch does not apply in $dir"
        else
          git -C "$src" apply --whitespace=nowarn "$repo/patches/$patch" || fail "$patch does not apply"
        fi ;;
      fifa/*)
        if ! git -C "$src" tag -l mcla-base | grep -q .; then
          git -C "$src" add -A && git "${ident[@]}" -C "$src" commit -qm "MCLA base: patches/mcla/series" &&
            git -C "$src" tag mcla-base
        fi
        git "${ident[@]}" -C "$src" am -q --whitespace=nowarn "$repo/patches/$patch" || fail "$patch does not apply" ;;
    esac
    echo "$(hash_of "$repo/patches/$patch") $patch" >> "$records.partial"
  done < <(patch_list)
  mv "$records.partial" "$records"
else
  stale=0
  while read -r patch dir; do
    recorded=$(grep " $patch\$" "$records" | cut -d' ' -f1 || true)
    if [ -z "$recorded" ]; then echo "not applied: $patch" >&2; stale=1
    elif [ "$recorded" != "$(hash_of "$repo/patches/$patch")" ]; then echo "changed since applied: $patch" >&2; stale=1
    fi
  done < <(patch_list)
  [ $stale = 0 ] || fail "the SDK does not match patches/ (delete $src and run this again)"
fi
[ -n "$check_only" ] && { echo "the SDK matches patches/"; exit 0; }

echo "==> building the SDK ($config; the long step, once)"
if [ ! -f "$build/build.ninja" ]; then
  logged sdk-configure cmake -S "$src" --preset mac-arm64 \
    -DREXGLUE_USE_VULKAN=ON -DREXGLUE_ENABLE_TRACY=OFF -DREXGLUE_ENABLE_FSR=OFF
fi
logged sdk-build cmake --build "$build" --config "$config" -j "$jobs"
logged sdk-install cmake --install "$build" --config "$config"
# The install registers itself in the user's CMake package registry; other projects must not find this SDK.
grep -rl "$src" "$HOME/.cmake/packages/rexglue" 2> /dev/null | xargs rm -f 2> /dev/null || true
echo "SDK ready: $src/out/install/mac-arm64"
