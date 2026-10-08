#!/usr/bin/env python3
# Biblioteki natywne sherpa-onnx bez TTS dla WS.Scribe (workflow native.yml).
#   python native.py check <plik>...                         — zero ciągów espeak/piper/phonemize/cppjieba (ASCII i UTF-16), jak `strings -a | grep -ci`
#   python native.py package <rid> <sherpa-onnx> <katalog> <out.zip> — biblioteki + BUILD-INFO.txt + licencje → zip
import hashlib, os, re, subprocess, sys, zipfile

BANNED = ["espeak", "piper", "phonemize", "cppjieba"]          # TTS: eSpeak NG (GPL-3.0+), piper-phonemize, cppjieba
INFO = ["general public license", "gpl"]                       # tylko do wglądu (nie przerywa)
LIBS = {
    "win-x64": ["sherpa-onnx-c-api.dll", "onnxruntime.dll"],
    "linux-x64": ["libsherpa-onnx-c-api.so", "libonnxruntime.so"],
    "linux-arm64": ["libsherpa-onnx-c-api.so", "libonnxruntime.so"],
}
# biblioteki systemowe, których wolno wymagać na Linuksie (reszta = błąd pakowania)
LINUX_OK = re.compile(r"^(libonnxruntime\.so|libstdc\+\+\.so\.6|libgcc_s\.so\.1|libm\.so\.6|libc\.so\.6|libpthread\.so\.0|libdl\.so\.2|librt\.so\.1|ld-linux-[\w-]+\.so\.\d)$")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def strings(data):
    # ciągi drukowalne ≥ 4 znaki, jak `strings -a`; plus UTF-16LE (Windows)
    for m in re.finditer(rb"[\x20-\x7e\t]{4,}", data):
        yield m.group().decode("ascii")
    for m in re.finditer(rb"(?:[\x20-\x7e\t]\x00){4,}", data):
        yield m.group()[::2].decode("ascii")


def scan(path):
    # raw = jak `strings -a | grep -ci słowo`; real = bez fałszywych trafień „…e” + „speaker” (np. CreateSpeakerEmbedding, OfflineSpeakerDiarization)
    with open(path, "rb") as f:
        data = f.read()
    raw = {w: 0 for w in BANNED + INFO}
    real = dict(raw)
    fp = []
    for s in strings(data):
        low = s.lower()
        for w in raw:
            if w in low:
                raw[w] += 1
                if w in (low.replace("speaker", "") if w == "espeak" else low):
                    real[w] += 1
                    if w in BANNED:
                        print(f"  TTS string in {os.path.basename(path)}: {s[:160]!r}")
                elif len(fp) < 12:
                    fp.append(s[:100])
    return raw, real, fp


def check(files):
    bad, out = 0, []
    for f in files:
        raw, real, fp = scan(f)
        line = (f"{os.path.basename(f)}: " + " ".join(f"{w}={real[w]}" for w in BANNED) +
                f"  (raw `strings | grep -ci espeak` = {raw['espeak']}, of which {raw['espeak'] - real['espeak']} only inside the word 'speaker')" +
                f"  gpl={raw['gpl']} general_public_license={raw['general public license']}  sha256={sha256(f)}")
        print(line)
        out.append(line)
        if fp:
            ex = "; ".join(fp)
            print(f"  'speaker' matches, e.g.: {ex}")
            out.append(f"  'speaker' matches, e.g.: {ex}")
        bad += sum(real[w] for w in BANNED)
    if bad:
        print("BŁĄD: w bibliotekach są ciągi TTS (espeak/piper/phonemize/cppjieba)", file=sys.stderr)
    return bad, out


def run(*cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def elf_info(path):
    # NEEDED, RPATH, najwyższe wymagane GLIBC/GLIBCXX (readelf/objdump z binutils na runnerze)
    d = run("readelf", "-d", path)
    needed = re.findall(r"\(NEEDED\)\s+Shared library: \[(.+?)\]", d)
    rpath = re.findall(r"\((?:RPATH|RUNPATH)\)\s+Library r(?:un)?path: \[(.+?)\]", d)
    t = run("objdump", "-T", path)
    def top(tag):
        v = sorted({tuple(int(x) for x in m.split(".")) for m in re.findall(tag + r"_([0-9.]+[0-9])", t)})
        return tag + "_" + ".".join(map(str, v[-1])) if v else "-"
    exports = len([l for l in run("nm", "-D", "--defined-only", path).splitlines() if " T SherpaOnnx" in l or " T SherpaOffline" in l])
    return needed, rpath, top("GLIBC"), top("GLIBCXX"), exports


def dep_sources(build):
    # źródła pobrane przez CMake (FetchContent) — adresy i sumy z _deps/<nazwa>-subbuild/CMakeLists.txt
    deps = os.path.join(build, "_deps")
    out = []
    for d in sorted(os.listdir(deps)):
        if not d.endswith("-src"):
            continue
        name = d[:-4]
        urls, hashes = [], []
        sub = os.path.join(deps, name + "-subbuild", "CMakeLists.txt")
        if os.path.exists(sub):
            txt = open(sub, encoding="utf-8", errors="replace").read()
            urls = list(dict.fromkeys(re.findall(r"https?://[^\s\"';]+", txt)))
            urls = [u for u in urls if "cmake.org" not in u and "gitlab.kitware" not in u]
            hashes = list(dict.fromkeys(re.findall(r"SHA256=[0-9a-fA-F]{64}", txt)))
        out.append((name, os.path.join(deps, d), urls, hashes))
    return out


def compiler(build):
    for root, _, files in os.walk(os.path.join(build, "CMakeFiles")):
        if "CMakeCXXCompiler.cmake" in files:
            t = open(os.path.join(root, "CMakeCXXCompiler.cmake"), encoding="utf-8", errors="replace").read()
            cid = re.search(r'set\(CMAKE_CXX_COMPILER_ID "(.*?)"\)', t)
            ver = re.search(r'set\(CMAKE_CXX_COMPILER_VERSION "(.*?)"\)', t)
            return f"{cid.group(1) if cid else '?'} {ver.group(1) if ver else '?'}"
    return "?"


def cache(build, key):
    m = re.search(rf"^{key}:\w+=(.*)$", open(os.path.join(build, "CMakeCache.txt"), encoding="utf-8").read(), re.M)
    return m.group(1) if m else "?"


LICENSE_FILE = re.compile(r"^(license|licence|copying|notice|thirdpartynotices)", re.I)


def package(rid, src, build, out):
    if cache(build, "SHERPA_ONNX_ENABLE_TTS") != "OFF":
        sys.exit("BŁĄD: SHERPA_ONNX_ENABLE_TTS nie jest OFF w CMakeCache.txt")
    libdir = os.path.join(build, "install", "lib")
    files = [os.path.realpath(os.path.join(libdir, n)) for n in LIBS[rid]]   # realpath: .so może być dowiązaniem
    deps = dep_sources(build)
    for name, *_ in deps:
        if any(w in name.lower() for w in BANNED + ["ucd"]):
            sys.exit(f"BŁĄD: źródło TTS w _deps: {name}")
    bad, checks = check(files)
    if bad:
        sys.exit(1)

    env = os.environ.get
    run_url = f"{env('GITHUB_SERVER_URL', 'https://github.com')}/{env('GITHUB_REPOSITORY', '?')}/actions/runs/{env('GITHUB_RUN_ID', '?')}"
    lines = [
        "WS.Scribe — sherpa-onnx native libraries WITHOUT text-to-speech (no eSpeak NG, no piper-phonemize)",
        "",
        f"rid:           {rid}",
        f"sherpa-onnx:   {env('SHERPA_ONNX_TAG', '?')} commit {env('SHERPA_ONNX_COMMIT', '?')}",
        f"               https://github.com/k2-fsa/sherpa-onnx/tree/{env('SHERPA_ONNX_COMMIT', '?')}",
        f"               only change to the source: version.cc stamped with git sha1/date (as upstream new-release.sh)",
        f"cmake options: {' '.join(env('CMAKE_OPTS', '').split())} {env('CMAKE_EXTRA', '')}".rstrip(),
        f"TTS in cache:  SHERPA_ONNX_ENABLE_TTS={cache(build, 'SHERPA_ONNX_ENABLE_TTS')}",
        f"compiler:      {compiler(build)}",
        f"cmake:         {cache(build, 'CMAKE_COMMAND')} ({env('CMAKE_VERSION_STR', '?')})",
        f"built on:      {env('BUILT_ON', '?')}",
        f"workflow run:  {run_url} (repo commit {env('GITHUB_SHA', '?')})",
        "",
        "files:",
    ]
    for n, f in zip(LIBS[rid], files):
        lines.append(f"  {n}  {os.path.getsize(f)} bytes  sha256 {sha256(f)}")
        if rid.startswith("linux"):
            needed, rpath, glibc, glibcxx, exports = elf_info(f)
            lines.append(f"    NEEDED {', '.join(needed)}; RPATH {', '.join(rpath) or '-'}; needs {glibc}, {glibcxx}" +
                         (f"; exported SherpaOnnx* functions: {exports}" if "sherpa" in n else ""))
            for x in needed:
                if not LINUX_OK.match(x):
                    sys.exit(f"BŁĄD: {n} wymaga {x}")
            if "sherpa" in n and rpath != ["$ORIGIN"]:
                sys.exit(f"BŁĄD: {n} ma RPATH {rpath}, oczekiwane $ORIGIN")
    lines += ["", "onnxruntime.* is the prebuilt ONNX Runtime fetched by sherpa-onnx's CMake (URL and SHA-256 below), not rebuilt here.", "",
              "third-party sources fetched by CMake (_deps), compiled in or linked:"]
    for name, _, urls, hashes in deps:
        lines.append(f"  {name}: {' '.join(urls) or '?'} {' '.join(hashes)}".rstrip())
    lines += ["", "string check (printable runs >= 4 chars as `strings -a`, ASCII + UTF-16LE, case-insensitive; espeak/piper/phonemize/cppjieba must be 0).",
              "A case-insensitive 'espeak' also matches the speaker-recognition API names ('...e' + 'Speaker...', e.g. SherpaOnnxCreateSpeakerEmbeddingExtractor,",
              "OfflineSpeakerDiarization); such strings are counted separately and are not eSpeak NG. Equivalent shell check:",
              "  strings -a <lib> | grep -i espeak | grep -vci speaker   -> 0;   strings -a <lib> | grep -ci piper -> 0"]
    lines += ["  " + c for c in checks]
    smoke = os.environ.get("SMOKE_FILE")
    if smoke and os.path.exists(smoke):
        lines += ["", "smoke test (same OfflineRecognizer config as WS.Scribe, Parakeet TDT 0.6B v3 int8, org.k2fsa.sherpa.onnx 1.13.8 .NET wrapper):"]
        lines += ["  " + l for l in open(smoke, encoding="utf-8").read().splitlines()]
    info = "\n".join(lines) + "\n"
    print(info)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n, f in zip(LIBS[rid], files):
            z.write(f, n)
        z.writestr("BUILD-INFO.txt", info)
        for f in os.listdir(src):
            if LICENSE_FILE.match(f) and os.path.isfile(os.path.join(src, f)):
                z.write(os.path.join(src, f), f"licenses/sherpa-onnx/{f}")
        for name, path, _, _ in deps:
            for f in sorted(os.listdir(path)):
                p = os.path.join(path, f)
                if LICENSE_FILE.match(f) and os.path.isfile(p):
                    z.write(p, f"licenses/{name}/{f}")
    print(f"{out}: {os.path.getsize(out)} bytes sha256 {sha256(out)}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        sys.exit(1 if check(sys.argv[2:])[0] else 0)
    if len(sys.argv) == 6 and sys.argv[1] == "package":
        package(*sys.argv[2:])
        sys.exit(0)
    sys.exit(__doc__ or "użycie: native.py check <plik>... | package <rid> <sherpa-onnx> <build> <out.zip>")
