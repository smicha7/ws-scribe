Native speech-recognition libraries used by WS.Scribe for Windows (from 0.1.2) and Linux. Not used by the macOS app.

Built by [`.github/workflows/native.yml`](https://github.com/smicha7/ws-scribe/blob/main/.github/workflows/native.yml) from **sherpa-onnx v1.13.8** ([commit 11afbd0](https://github.com/k2-fsa/sherpa-onnx/tree/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf)) — the same C API as the `org.k2fsa.sherpa.onnx` 1.13.8 .NET package — with `-DSHERPA_ONNX_ENABLE_TTS=OFF`: text-to-speech is not compiled in, so these libraries contain **no eSpeak NG and no piper-phonemize**.

| File | Contents |
|---|---|
| `native-win-x64.zip` | `sherpa-onnx-c-api.dll`, `onnxruntime.dll` — Windows 10/11 x64, MSVC, static CRT |
| `native-linux-x64.zip` | `libsherpa-onnx-c-api.so`, `libonnxruntime.so` — manylinux2014 (glibc 2.17+), RPATH `$ORIGIN` |
| `native-linux-arm64.zip` | the same for 64-bit ARM |
| `SHA256SUMS.txt` | SHA-256 of the three zips |

Each zip contains `BUILD-INFO.txt` (CMake options, compiler, build image, every third-party source URL with its SHA-256, the string check and the smoke-test result) and `licenses/` (license files of sherpa-onnx and of each third-party source).

Checks in every run: no `espeak`, `piper`, `phonemize` or `cppjieba` strings in either library (ASCII and UTF-16); no TTS sources fetched by CMake; on the same runner, the Parakeet TDT 0.6B v3 int8 model transcribes the model's test recordings to exactly the same text with these libraries as with the NuGet 1.13.8 libraries.

`onnxruntime` is ONNX Runtime 1.28.2 as prebuilt by the sherpa-onnx author ([csukuangfj/onnxruntime-libs v1.28.2](https://github.com/csukuangfj/onnxruntime-libs/releases/tag/v1.28.2)) and downloaded by sherpa-onnx's CMake with a fixed SHA-256; it is not rebuilt here.

Source code: [sherpa-onnx v1.13.8](https://github.com/k2-fsa/sherpa-onnx/tree/v1.13.8) (Apache-2.0) · [ONNX Runtime v1.28.2](https://github.com/microsoft/onnxruntime/tree/v1.28.2) (MIT) · other components with exact URLs in `BUILD-INFO.txt`.

Rebuild: Actions → native → Run workflow (or `gh workflow run native.yml --repo smicha7/ws-scribe`). The checks are reproducible; the binaries are not byte-identical between runs (build timestamps).

This is a pre-release and never the "latest" release.
