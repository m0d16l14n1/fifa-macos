# Licences

| What | Licence |
|---|---|
| This project's own code: `src/`, `scripts/`, `launcher/`, `config/`, the build files | MIT ([`../LICENSE`](../LICENSE)) |
| ReXGlue SDK (cloned by `scripts/sdk.sh`, not in git) | BSD 3-Clause, with Xenia's notice ([`ReXGlue-BSD-3-Clause.txt`](ReXGlue-BSD-3-Clause.txt)) |
| `patches/mcla/`: the mcla-recomp patch series (RenanQueiroz and the mcla-recomp contributors) | GPL-3.0-or-later ([`GPL-3.0.txt`](GPL-3.0.txt)); parts ported from MIT projects are listed in [`mcla-recomp-THIRD-PARTY-NOTICES.md`](mcla-recomp-THIRD-PARTY-NOTICES.md) |
| `patches/fifa/`: FIFA 19's changes to the SDK, on top of `patches/mcla/` | GPL-3.0-or-later, like the code they change |

The SDK built from these patches, and any program linked with it, is under the GPL as a whole: whoever
distributes a build has to offer its source under GPL-3.0-or-later.

`src/native_libc_hooks.cpp` and the codegen fixes in `patches/fifa/0001-*` come from ReStreet (FIFA Street 2012 for
PC, MIT, SamuelitoDaVila and contributors), which this repository started as.

Nothing of FIFA 19 is in this repository. FIFA, EA SPORTS and the game's content belong to Electronic Arts; Xbox
360 to Microsoft. This project is not affiliated with or endorsed by either, and its licences grant no rights to
the game or to anything made from it.
