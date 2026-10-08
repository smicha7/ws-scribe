// Test dymny bibliotek natywnych (workflow native.yml): ta sama konfiguracja OfflineRecognizer co WS.Scribe
// (Parakeet TDT 0.6B v3 int8, greedy_search), plik WAV → tekst. Wypisuje też, które biblioteki zostały wczytane (ścieżka + SHA-256).
// Użycie: dotnet NativeSmoke.dll <folder modelu> <plik.wav>...
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using SherpaOnnx;

Console.OutputEncoding = Encoding.UTF8;
if (args.Length < 2) { Console.Error.WriteLine("usage: NativeSmoke <model dir> <file.wav>..."); return 2; }
string dir = args[0];
NativeLibrary.TryLoad("onnxruntime", typeof(Program).Assembly, null, out _);   // jak Engine.cs: onnxruntime z folderu aplikacji, pierwsze

var c = new OfflineRecognizerConfig();
c.ModelConfig.Transducer.Encoder = Path.Combine(dir, "encoder.int8.onnx");
c.ModelConfig.Transducer.Decoder = Path.Combine(dir, "decoder.int8.onnx");
c.ModelConfig.Transducer.Joiner = Path.Combine(dir, "joiner.int8.onnx");
c.ModelConfig.Tokens = Path.Combine(dir, "tokens.txt");
c.ModelConfig.ModelType = "nemo_transducer";
c.ModelConfig.NumThreads = 2;   // stała liczba wątków — porównujemy dwa przebiegi bajt w bajt
c.DecodingMethod = "greedy_search";
using var rec = new OfflineRecognizer(c);

Console.WriteLine($"version sherpa-onnx {VersionInfo.Version} git {VersionInfo.GitSha1} ({VersionInfo.GitDate}); onnxruntime {VersionInfo.OnnxruntimeVersion}");
// wczytane biblioteki: Linux — /proc/self/maps (pewne także dla dlopen), Windows — lista modułów procesu
var loaded = OperatingSystem.IsLinux()
    ? File.ReadLines("/proc/self/maps").Select(l => l.IndexOf('/') is var i and >= 0 ? l[i..] : "")
    : Process.GetCurrentProcess().Modules.Cast<ProcessModule>().Select(m => m.FileName);
foreach (var f in loaded.Where(f => f != "").Distinct())
    if (Path.GetFileName(f) is var n && (n.Contains("sherpa-onnx", StringComparison.OrdinalIgnoreCase) || n.Contains("onnxruntime", StringComparison.OrdinalIgnoreCase)))
        Console.WriteLine($"lib {n} {Sha(f)} {f}");

foreach (var wav in args[1..])
{
    var (rate, s) = ReadWav(wav);
    var sw = Stopwatch.StartNew();
    using var st = rec.CreateStream();
    st.AcceptWaveform(rate, s);
    rec.Decode(st);
    Console.WriteLine($"text {Path.GetFileName(wav)}: {st.Result.Text.Trim()}");
    Console.Error.WriteLine($"{Path.GetFileName(wav)}: {s.Length / (double)rate:F1} s audio, {sw.ElapsedMilliseconds} ms");
}
return 0;

static string Sha(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();

// WAV PCM 16-bit albo float 32-bit, dowolna liczba kanałów (średnia) — sherpa-onnx sam przelicza częstotliwość.
static (int, float[]) ReadWav(string path)
{
    var b = File.ReadAllBytes(path);
    int ch = 1, rate = 16_000, bits = 16, p = 12;
    while (p + 8 <= b.Length)
    {
        string id = Encoding.ASCII.GetString(b, p, 4);
        int n = BitConverter.ToInt32(b, p + 4);
        p += 8;
        if (id == "fmt ")
        {
            ch = BitConverter.ToUInt16(b, p + 2);
            rate = BitConverter.ToInt32(b, p + 4);
            bits = BitConverter.ToUInt16(b, p + 14);
        }
        else if (id == "data")
        {
            n = Math.Min(n, b.Length - p);
            int step = bits / 8 * ch, frames = n / step;
            var s = new float[frames];
            for (int i = 0; i < frames; i++)
            {
                float sum = 0;
                for (int k = 0; k < ch; k++)
                {
                    int o = p + i * step + k * bits / 8;
                    sum += bits == 16 ? BitConverter.ToInt16(b, o) / 32768f : BitConverter.ToSingle(b, o);
                }
                s[i] = sum / ch;
            }
            return (rate, s);
        }
        p += n + (n & 1);
    }
    throw new InvalidDataException("no data chunk: " + path);
}
