#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <string>
#include <vector>
#include <unordered_map>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <cstdio>

// x86 hooks for the byte-based DFBHD glyph renderer. The archive builder stores
// marked UTF-8 in RTXT; this DLL turns each Thai grapheme into a carrier byte,
// then updates that byte's FNT0 descriptor just before measure/draw.
struct Glyph { uint8_t page; float uv[4]; };
struct HeightAtlas { uint8_t height, pages, basePages; std::unordered_map<std::string, Glyph> glyphs; };
struct LineMap { std::string bytes; std::vector<int> glyphAt; };
struct SavedDesc { uint8_t code; uint32_t words[5]; };

static std::vector<uint8_t> gCarriers;
static std::unordered_map<int, HeightAtlas> gAtlases;
static std::vector<LineMap> gLines;
static std::vector<SavedDesc> gSaved;
static std::vector<uint8_t> gSavedCode(256, 0);
static std::string gEncoded;
static const char gEmptyText[] = "";
static int gFontHeight = 0;
static int gAtlasBasePage = 0;
static uintptr_t gFontThis = 0;
static bool gActive = false;
static bool gEnableGlyphPatch = true;
static bool gLoggedThaiDraw = false;
static bool gLoggedThaiProfile = false;
static int gMeasureLine = -1;
static const char* gMeasurePtr = nullptr;
static void* gDrawTrampoline = nullptr;
static void* gMeasureEntryTrampoline = nullptr;
static void* gWrapDrawTrampoline = nullptr;
static void* gWrapDraw2DTrampoline = nullptr;
static void* gUiWrapDrawTrampoline = nullptr;
static uintptr_t gMeasureAddr = 0;
static uintptr_t gDrawContinue = 0;
static uintptr_t gMeasureMidContinue = 0;
static DWORD gDrawTls = TLS_OUT_OF_INDEXES;
static DWORD gMeasureTls = TLS_OUT_OF_INDEXES;
static HMODULE gRealD3D8 = nullptr;
static FARPROC gRealCreate8 = nullptr;
static CRITICAL_SECTION gPatchLock;
static bool gLockReady = false;

static void log_line(const char* text) {
    HANDLE f = CreateFileW(L"thai_runtime.log", FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                           nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return;
    DWORD wrote = 0; WriteFile(f, text, static_cast<DWORD>(strlen(text)), &wrote, nullptr);
    WriteFile(f, "\r\n", 2, &wrote, nullptr); CloseHandle(f);
}

struct DrawCallStack { uintptr_t callers[128]; bool ownsPatch[128]; bool pendingOwner; unsigned depth; };
struct MeasureReturnStack { uintptr_t callers[64]; unsigned depth; };
extern "C" void __cdecl push_measure_caller(uintptr_t caller) {
    if (gMeasureTls == TLS_OUT_OF_INDEXES) return;
    auto* stack = static_cast<MeasureReturnStack*>(TlsGetValue(gMeasureTls));
    if (!stack) {
        stack = static_cast<MeasureReturnStack*>(HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(MeasureReturnStack)));
        if (!stack || !TlsSetValue(gMeasureTls, stack)) { if (stack) HeapFree(GetProcessHeap(), 0, stack); return; }
    }
    if (stack->depth < 64) stack->callers[stack->depth++] = caller;
}
extern "C" uintptr_t __cdecl pop_measure_caller() {
    if (gMeasureTls == TLS_OUT_OF_INDEXES) return 0;
    auto* stack = static_cast<MeasureReturnStack*>(TlsGetValue(gMeasureTls));
    if (!stack || !stack->depth) return 0;
    return stack->callers[--stack->depth];
}
static DrawCallStack* draw_stack() {
    if (gDrawTls == TLS_OUT_OF_INDEXES) return nullptr;
    auto* stack = static_cast<DrawCallStack*>(TlsGetValue(gDrawTls));
    if (!stack) {
        stack = static_cast<DrawCallStack*>(HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(DrawCallStack)));
        if (!stack || !TlsSetValue(gDrawTls, stack)) { if (stack) HeapFree(GetProcessHeap(), 0, stack); return nullptr; }
    }
    return stack;
}
extern "C" void __cdecl begin_draw_call() {
    auto* stack = draw_stack();
    if (stack) stack->pendingOwner = false;
}
static void mark_draw_owner() {
    auto* stack = draw_stack();
    if (stack) stack->pendingOwner = true;
}
static bool current_draw_owns_patch() {
    auto* stack = draw_stack();
    return stack && stack->depth && stack->ownsPatch[stack->depth - 1];
}
extern "C" void __cdecl push_draw_caller(uintptr_t caller) {
    auto* stack = draw_stack();
    if (stack && stack->depth < 128) {
        stack->callers[stack->depth] = caller;
        stack->ownsPatch[stack->depth] = stack->pendingOwner;
        ++stack->depth;
        stack->pendingOwner = false;
    }
}
extern "C" uintptr_t __cdecl pop_draw_caller() {
    if (gDrawTls == TLS_OUT_OF_INDEXES) return 0;
    auto* stack = static_cast<DrawCallStack*>(TlsGetValue(gDrawTls));
    if (!stack || !stack->depth) return 0;
    return stack->callers[--stack->depth];
}

static bool read_exact(HANDLE f, void* p, DWORD n) {
    DWORD got = 0;
    return ReadFile(f, p, n, &got, nullptr) && got == n;
}

static bool load_map() {
    HANDLE f = CreateFileW(L"thai_glyph_map.bin", GENERIC_READ, FILE_SHARE_READ,
                           nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return false;
    DWORD size = GetFileSize(f, nullptr);
    if (size < 10 || size > 16 * 1024 * 1024) { CloseHandle(f); return false; }
    std::vector<uint8_t> b(size);
    bool ok = read_exact(f, b.data(), size);
    CloseHandle(f);
    if (!ok || memcmp(b.data(), "THM1", 4)) return false;
    size_t p = 4;
    uint16_t clusterCount = *reinterpret_cast<uint16_t*>(&b[p]); p += 2;
    uint16_t carrierCount = *reinterpret_cast<uint16_t*>(&b[p]); p += 2;
    uint16_t heightCount = *reinterpret_cast<uint16_t*>(&b[p]); p += 2;
    if (!clusterCount || !carrierCount || carrierCount > 224 || heightCount > 64 || p + carrierCount + heightCount * 3 > b.size()) return false;
    gCarriers.assign(b.begin() + p, b.begin() + p + carrierCount); p += carrierCount;
    for (uint16_t i = 0; i < heightCount; ++i) {
        HeightAtlas a; a.height = b[p++]; a.pages = b[p++]; a.basePages = b[p++];
        if (!a.height || !a.pages) return false;
        gAtlases.emplace(a.height, std::move(a));
    }
    for (uint16_t hi = 0; hi < heightCount; ++hi) {
        // The builder writes cluster records in deterministic lexical order.
        int height = 0;
        for (auto& pair : gAtlases) if (pair.second.glyphs.size() == 0) {
            // Records are grouped in ascending height order.
            if (!height || pair.first < height) height = pair.first;
        }
        // Select the hi-th height in the same order as the builder.
        std::vector<int> hs; for (auto& pair : gAtlases) hs.push_back(pair.first);
        std::sort(hs.begin(), hs.end());
        height = hs[hi];
        auto& atlas = gAtlases[height];
        for (uint16_t ci = 0; ci < clusterCount; ++ci) {
            if (p + 3 > b.size()) return false;
            uint8_t recH = b[p++], len = b[p++], page = b[p++];
            if (recH != height || !len || len > 64 || p + len + 16 > b.size() || page >= atlas.pages) return false;
            std::string cluster(reinterpret_cast<char*>(&b[p]), len); p += len;
            Glyph g{}; g.page = page; memcpy(g.uv, &b[p], 16); p += 16;
            atlas.glyphs.emplace(std::move(cluster), g);
        }
    }
    return p == b.size();
}

static bool thai_lead(uint32_t cp) { return cp >= 0x0e40 && cp <= 0x0e44; }
static bool thai_base(uint32_t cp) { return cp >= 0x0e01 && cp <= 0x0e2e; }
static bool thai_mark(uint32_t cp) { return (cp >= 0x0e31 && cp <= 0x0e3a) || (cp >= 0x0e47 && cp <= 0x0e4e) || cp == 0x0e33; }

struct Unit { uint32_t cp; std::string utf8; };
static bool decode_utf8(const char*& p, uint32_t& cp, std::string& bytes) {
    const unsigned char* s = reinterpret_cast<const unsigned char*>(p);
    if (!*s) return false;
    if (*s < 0x80) {
        cp = s[0];
        bytes.assign(reinterpret_cast<const char*>(s), 1);
        p += 1;
        return true;
    }
    size_t n = (*s & 0xe0) == 0xc0 ? 2 : ((*s & 0xf0) == 0xe0 ? 3 : ((*s & 0xf8) == 0xf0 ? 4 : 1));
    bool valid = n > 1;
    for (size_t i = 1; i < n; ++i) {
        if (!s[i] || (s[i] & 0xc0) != 0x80) { valid = false; break; }
    }
    if (!valid) {
        cp = 0xFFFD;
        bytes.assign(reinterpret_cast<const char*>(s), 1);
        p += 1;
        return true;
    }
    cp = (n == 2 ? ((s[0] & 0x1f) << 6) | (s[1] & 0x3f)
                 : (n == 3 ? ((s[0] & 0x0f) << 12) | ((s[1] & 0x3f) << 6) | (s[2] & 0x3f)
                           : ((s[0] & 7) << 18) | ((s[1] & 0x3f) << 12) | ((s[2] & 0x3f) << 6) | (s[3] & 0x3f)));
    bytes.assign(reinterpret_cast<const char*>(s), n);
    p += n;
    return true;
}

static int find_line(const char* line) {
    if (!line) return -1;
    size_t len = strlen(line);
    for (size_t i = 0; i < gLines.size(); ++i) {
        if (gLines[i].bytes.size() == len && memcmp(gLines[i].bytes.data(), line, len) == 0) return static_cast<int>(i);
    }
    return -1;
}

static void save_descriptor(uint8_t code) {
    if (gSavedCode[code]) return;
    uintptr_t addr = gFontThis - 0x114 + static_cast<uintptr_t>(code) * 20;
    SavedDesc s{}; s.code = code; memcpy(s.words, reinterpret_cast<void*>(addr), 20);
    gSaved.push_back(s); gSavedCode[code] = 1;
}

static void patch_for_position(uintptr_t fontThis, const char* line, int index, uint8_t code, int lineId) {
    if (!gEnableGlyphPatch || !gActive || fontThis != gFontThis || !line || lineId < 0 || lineId >= static_cast<int>(gLines.size()) || index < 0) return;
    const auto& lm = gLines[lineId];
    if (static_cast<size_t>(index) >= lm.glyphAt.size() || static_cast<size_t>(index) >= lm.bytes.size() ||
        static_cast<uint8_t>(lm.bytes[index]) != code) return;
    int glyphId = lm.glyphAt[index];
    if (glyphId < 0) return;
    auto ai = gAtlases.find(gFontHeight);
    if (ai == gAtlases.end()) return;
    // Glyph IDs are resolved below from the per-line UTF-8 side table.
    extern std::vector<std::vector<std::string>> gLineClusters;
    if (static_cast<size_t>(lineId) >= gLineClusters.size() || static_cast<size_t>(glyphId) >= gLineClusters[lineId].size()) return;
    auto it = ai->second.glyphs.find(gLineClusters[lineId][glyphId]);
    if (it == ai->second.glyphs.end()) return;
    save_descriptor(code);
    uint32_t words[5];
    words[0] = static_cast<uint32_t>(gAtlasBasePage + it->second.page);
    memcpy(&words[1], it->second.uv, 16);
    memcpy(reinterpret_cast<void*>(gFontThis - 0x114 + static_cast<uintptr_t>(code) * 20), words, 20);
}

std::vector<std::vector<std::string>> gLineClusters;

static bool is_cp874_thai(uint8_t b) {
    return (b >= 0xA1 && b <= 0xDA) || (b >= 0xDF && b <= 0xFB);
}

static std::string normalize_thai_input(const char* input) {
    std::string out;
    if (!input) return out;
    const char* p = input;
    while (*p) {
        if (strncmp(p, "\x01THAI\x01", 6) == 0) {
            p += 6;
            continue;
        }
        uint8_t b = static_cast<uint8_t>(*p);
        if (b < 0x80) {
            out.push_back(*p++);
            continue;
        }
        const char* next = p;
        uint32_t cp = 0;
        std::string unit;
        if (decode_utf8(next, cp, unit) && cp != 0xFFFD) {
            out += unit;
            p = next;
            continue;
        }
        if (is_cp874_thai(b)) {
            uint32_t ucp = 0x0E00u + static_cast<uint32_t>(b - 0xA0u);
            out.push_back(static_cast<char>(0xE0u | (ucp >> 12)));
            out.push_back(static_cast<char>(0x80u | ((ucp >> 6) & 0x3Fu)));
            out.push_back(static_cast<char>(0x80u | (ucp & 0x3Fu)));
        }
        ++p;
    }
    return out;
}

static bool contains_thai_utf8(const char* input) {
    if (!input) return false;
    const char* p = input;
    uint32_t cp;
    std::string unit;
    while (*p) {
        if (strncmp(p, "\x01THAI\x01", 6) == 0) return true;
        uint8_t b = static_cast<uint8_t>(*p);
        if (b < 0x80) { ++p; continue; }
        const char* next = p;
        if (decode_utf8(next, cp, unit) && cp != 0xFFFD) {
            if (cp >= 0x0e00 && cp <= 0x0e7f) return true;
            p = next;
            continue;
        }
        if (is_cp874_thai(b)) return true;
        ++p;
    }
    return false;
}

static const char* prepare_draw(uintptr_t fontThis, const char* input) {
    if (!input || gActive) return input;
    bool hasMarker = (strncmp(input, "\x01THAI\x01", 6) == 0);
    if (hasMarker && strncmp(input + 6, "\x01HIDE\x01", 6) == 0) return gEmptyText;
    if (!hasMarker && !contains_thai_utf8(input)) return input;
    if (!gLoggedThaiDraw) { log_line("Thai marker reached draw hook"); gLoggedThaiDraw = true; }
    EnterCriticalSection(&gPatchLock);
    gActive = true; gFontThis = fontThis; gSaved.clear(); std::fill(gSavedCode.begin(), gSavedCode.end(), 0);
    gLines.clear(); gLineClusters.clear(); gEncoded.clear(); gMeasureLine = -1;
    float v0 = *reinterpret_cast<float*>(fontThis - 0x114 + 'H' * 20 + 8);
    float v1 = *reinterpret_cast<float*>(fontThis - 0x114 + 'H' * 20 + 16);
    gFontHeight = static_cast<int>(std::lround((v1 - v0) * 256.0f));
    auto ai = gAtlases.find(gFontHeight);
    if (!gLoggedThaiProfile || ai == gAtlases.end()) {
        char profile[96]; sprintf_s(profile, "Thai font profile %s: height=%d base pages=%u",
            ai == gAtlases.end() ? "missing" : "found", gFontHeight, ai == gAtlases.end() ? 0 : ai->second.basePages);
        log_line(profile); gLoggedThaiProfile = true;
    }
    if (ai == gAtlases.end()) { gActive = false; LeaveCriticalSection(&gPatchLock); return input; }
    gAtlasBasePage = ai->second.basePages;
    std::vector<Unit> units;
    std::string clean = normalize_thai_input(input);
    const char* p = clean.c_str();
    uint32_t cp; std::string u8;
    while (decode_utf8(p, cp, u8)) units.push_back({cp, u8});
    size_t carrierIndex = 0;
    LineMap line; std::vector<std::string> lineClusters;
    auto flush_line = [&]() { gLines.push_back(std::move(line)); gLineClusters.push_back(std::move(lineClusters)); line = LineMap{}; lineClusters = {}; };
    for (size_t i = 0; i < units.size();) {
        if (units[i].cp == '\r') { gEncoded.push_back('\r'); ++i; continue; }
        if (units[i].cp == '\n') { gEncoded.push_back('\n'); flush_line(); ++i; continue; }
        if (units[i].cp == 0xFFFD) { ++i; continue; }
        size_t j = i + 1;
        if (thai_lead(units[i].cp) && j < units.size() && thai_base(units[j].cp)) ++j;
        while (j < units.size() && thai_mark(units[j].cp)) ++j;
        std::string cluster;
        for (size_t k = i; k < j; ++k) cluster += units[k].utf8;
        bool needsGlyph = units[i].cp > 0x7f;
        if (!needsGlyph) {
            gEncoded += cluster; line.bytes += cluster;
            for (size_t k = 0; k < cluster.size(); ++k) line.glyphAt.push_back(-1);
        } else {
            auto gi = ai->second.glyphs.find(cluster);
            if (gi == ai->second.glyphs.end()) {
                static bool loggedMissing = false;
                if (!loggedMissing) {
                    char msg[160]; sprintf_s(msg, "WARN: missing glyph cluster at height=%d bytes=%u", gFontHeight, static_cast<unsigned>(cluster.size()));
                    log_line(msg);
                    loggedMissing = true;
                }
                gEncoded.push_back(' '); line.bytes.push_back(' '); line.glyphAt.push_back(-1);
            } else {
                int id = static_cast<int>(lineClusters.size()); lineClusters.push_back(cluster);
                uint8_t c = gCarriers[carrierIndex++ % gCarriers.size()];
                gEncoded.push_back(static_cast<char>(c)); line.bytes.push_back(static_cast<char>(c)); line.glyphAt.push_back(id);
            }
        }
        i = j;
    }
    flush_line();
    mark_draw_owner();
    return gEncoded.c_str();
}

static void restore_active_patch();
static void restore_draw() {
    if (!gActive || !current_draw_owns_patch()) return;
    restore_active_patch();
}

static const char* prepare_measure(uintptr_t fontThis, const char* input) {
    if (!input || gActive) return input;
    if (strncmp(input, "\x01THAI\x01", 6) == 0) return prepare_draw(fontThis, input);
    if (!contains_thai_utf8(input)) return input;
    std::string marked("\x01THAI\x01", 6);
    marked += input;
    const char* result = prepare_draw(fontThis, marked.c_str());
    return result == marked.c_str() ? input : result;
}

static void restore_active_patch() {
    if (!gActive) return;
    for (const auto& s : gSaved) memcpy(reinterpret_cast<void*>(gFontThis - 0x114 + static_cast<uintptr_t>(s.code) * 20), s.words, 20);
    gSaved.clear(); std::fill(gSavedCode.begin(), gSavedCode.end(), 0);
    gLines.clear(); gLineClusters.clear(); gEncoded.clear(); gActive = false; gMeasureLine = -1;
    LeaveCriticalSection(&gPatchLock);
}

static void start_measure(uintptr_t fontThis, const char* line) {
    if (!gActive || fontThis != gFontThis) { gMeasureLine = -1; gMeasurePtr = nullptr; return; }
    gMeasurePtr = line;
    gMeasureLine = find_line(line);
}

static void patch_draw_char(uintptr_t fontThis, const char* line, int index, uint8_t code) {
    if (!gEnableGlyphPatch || !gActive) return;
    int li = find_line(line);
    patch_for_position(fontThis, line, index, code, li);
}

static void patch_measure_char(uintptr_t fontThis, uint8_t code, const char* afterChar) {
    if (!gActive || gMeasureLine < 0 || gMeasureLine >= static_cast<int>(gLines.size()) || !afterChar) return;
    ptrdiff_t idx = afterChar - gMeasurePtr - 1;
    const char* base = gLines[gMeasureLine].bytes.c_str();
    patch_for_position(fontThis, base, static_cast<int>(idx), code, gMeasureLine);
}

static void* make_trampoline(uintptr_t target, const uint8_t* expected, size_t n) {
    if (memcmp(reinterpret_cast<void*>(target), expected, n) != 0) return nullptr;
    uint8_t* t = static_cast<uint8_t*>(VirtualAlloc(nullptr, n + 5, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
    if (!t) return nullptr;
    memcpy(t, reinterpret_cast<void*>(target), n);
    t[n] = 0xE9; *reinterpret_cast<int32_t*>(t + n + 1) = static_cast<int32_t>((target + n) - (reinterpret_cast<uintptr_t>(t) + n + 5));
    return t;
}

static bool install_jump(uintptr_t target, void* hook, size_t length) {
    DWORD old = 0;
    if (!VirtualProtect(reinterpret_cast<void*>(target), length, PAGE_EXECUTE_READWRITE, &old)) return false;
    uint8_t* p = reinterpret_cast<uint8_t*>(target); p[0] = 0xE9;
    *reinterpret_cast<int32_t*>(p + 1) = static_cast<int32_t>(reinterpret_cast<uintptr_t>(hook) - (target + 5));
    for (size_t i = 5; i < length; ++i) p[i] = 0x90;
    FlushInstructionCache(GetCurrentProcess(), p, length);
    DWORD ignored; VirtualProtect(p, length, old, &ignored);
    return true;
}

extern "C" __declspec(naked) void HookDraw() {
    __asm {
        pushfd
        pushad
        call begin_draw_call
        mov eax, dword ptr [esp+18h]
        mov edx, dword ptr [esp+34h]
        push edx
        push eax
        call prepare_draw
        add esp, 8
        mov dword ptr [esp+34h], eax
        mov eax, dword ptr [esp+24h]
        push eax
        call push_draw_caller
        add esp, 4
        mov dword ptr [esp+24h], offset DrawReturn
        popad
        popfd
        jmp dword ptr [gDrawTrampoline]
    DrawReturn:
        push eax
        call restore_draw
        pop eax
        push eax
        call pop_draw_caller
        mov edx, eax
        pop eax
        jmp edx
    }
}

extern "C" void MeasureReturn();
extern "C" __declspec(naked) void HookMeasureEntry() {
    __asm {
        pushfd
        pushad
        mov eax, dword ptr [esp+18h]
        // Measure's first argument at original ESP+4 is the string to measure.
        mov edx, dword ptr [esp+28h]
        push edx
        push eax
        call prepare_measure
        add esp, 8
        mov edx, dword ptr [esp+28h]
        cmp eax, edx
        je MeasureNoTemporary
        mov dword ptr [esp+28h], eax
        mov ecx, dword ptr [esp+18h]
        push eax
        push ecx
        call start_measure
        add esp, 8
        mov eax, dword ptr [esp+24h]
        push eax
        call push_measure_caller
        add esp, 4
        mov dword ptr [esp+24h], offset MeasureReturn
        jmp MeasureReady
    MeasureNoTemporary:
        mov ecx, dword ptr [esp+18h]
        push edx
        push ecx
        call start_measure
        add esp, 8
    MeasureReady:
        popad
        popfd
        jmp dword ptr [gMeasureEntryTrampoline]
    }
}

extern "C" __declspec(naked) void MeasureReturn() {
    __asm {
        push eax
        call restore_active_patch
        call pop_measure_caller
        mov edx, eax
        pop eax
        jmp edx
    }
}

extern "C" __declspec(naked) void HookMeasureChar() {
    __asm {
        pushfd
        pushad
        mov eax, dword ptr [esp+04h]
        mov ecx, dword ptr [esp+3ch]
        mov edx, dword ptr [esp+00h]
        push edx
        push ecx
        push eax
        call patch_measure_char
        add esp, 12
        popad
        popfd
        mov eax, dword ptr [esp+18h]
        and eax, 0ffh
        lea edx, [eax+eax*4]
        jmp dword ptr [gMeasureMidContinue]
    }
}

extern "C" __declspec(naked) void HookDrawChar() {
    __asm {
        pushfd
        pushad
        mov eax, dword ptr [esp+38h]
        lea edx, [esp+268h]
        mov ecx, dword ptr [esp+94h]
        mov ebx, dword ptr [esp+0a4h]
        push ebx
        push ecx
        push edx
        push eax
        call patch_draw_char
        add esp, 16
        popad
        popfd
        mov eax, dword ptr [esp+80h]
        mov edx, dword ptr [esp+14h]
        jmp dword ptr [gDrawContinue]
    }
}

typedef int (__thiscall *MeasureTextFn)(uintptr_t fontThis, const char* text, int* outSize, void* style);
typedef int (__cdecl *WrapDrawFn)(char* text, int* fontWrapper, int x0, int y0, int x1, int y1, int align, uint32_t color, int startLine);
typedef int (__cdecl *WrapDraw2DFn)(char* text, uintptr_t fontThis, int x0, int y0, int x1, int y1, int align, uint32_t color, int startLine, int p10, int p11);
typedef void (__cdecl *UiWrapDrawFn)(char* text, uintptr_t fontObj, int x0, int y0, int boxW, int boxH, int colorMode, int align, int p9, float scale, int startLine);

static int measure_thai_width(uintptr_t fontThis, const std::string& text) {
    if (!gMeasureAddr || text.empty()) return 0;
    int sz[2] = {0, 0};
    reinterpret_cast<MeasureTextFn>(gMeasureAddr)(fontThis, text.c_str(), sz, nullptr);
    return sz[0];
}

static std::vector<char> wrap_thai_for_box(uintptr_t fontThis, const char* input, int maxWidth, bool emitCrLf = true) {
    std::vector<char> out;
    if (!input) { out.push_back('\0'); return out; }
    std::string clean = normalize_thai_input(input);
    const char* p = clean.c_str();
    std::vector<Unit> units;
    uint32_t cp = 0;
    std::string u8;
    while (decode_utf8(p, cp, u8)) {
        if (cp != '\r' && cp != 0xFFFD) units.push_back({cp, u8});
    }
    auto emit_line = [&](const std::string& line) {
        out.insert(out.end(), line.begin(), line.end());
        if (emitCrLf) out.push_back('\r');
        out.push_back('\n');
    };
    size_t i = 0;
    while (i < units.size()) {
        // Collect one paragraph up to '\n'
        std::vector<std::string> tokens;
        while (i < units.size() && units[i].cp != '\n') {
            if (units[i].cp == '<') {
                size_t j = i + 1;
                while (j < units.size() && units[j].cp != '>' && units[j].cp != '\n') ++j;
                if (j < units.size() && units[j].cp == '>') ++j;
                std::string tag;
                for (size_t k = i; k < j; ++k) tag += units[k].utf8;
                tokens.push_back(std::move(tag));
                i = j;
                continue;
            }
            size_t j = i + 1;
            if (thai_lead(units[i].cp) && j < units.size() && thai_base(units[j].cp)) ++j;
            while (j < units.size() && thai_mark(units[j].cp)) ++j;
            std::string cluster;
            for (size_t k = i; k < j; ++k) cluster += units[k].utf8;
            tokens.push_back(std::move(cluster));
            i = j;
        }
        if (i < units.size() && units[i].cp == '\n') ++i;

        if (tokens.empty()) {
            emit_line("");
            continue;
        }
        std::string cur;
        int lastSpaceTok = -1;
        std::string beforeSpace;
        for (size_t ti = 0; ti < tokens.size(); ++ti) {
            const std::string& tok = tokens[ti];
            if (tok == " ") {
                lastSpaceTok = static_cast<int>(ti);
                beforeSpace = cur;
            }
            std::string cand = cur + tok;
            if (maxWidth > 0 && !cur.empty() && tok != " " && measure_thai_width(fontThis, cand) > maxWidth) {
                if (lastSpaceTok >= 0 && !beforeSpace.empty()) {
                    emit_line(beforeSpace);
                    cur.clear();
                    for (size_t r = static_cast<size_t>(lastSpaceTok + 1); r <= ti; ++r) cur += tokens[r];
                } else {
                    emit_line(cur);
                    cur = tok;
                }
                lastSpaceTok = -1;
                beforeSpace.clear();
            } else {
                cur = std::move(cand);
            }
        }
        if (!cur.empty()) emit_line(cur);
    }
    if (emitCrLf) {
        if (out.size() >= 2 && out[out.size() - 2] == '\r' && out[out.size() - 1] == '\n') {
            out.resize(out.size() - 2);
        }
    } else if (!out.empty() && out.back() == '\n') {
        out.pop_back();
    }
    out.push_back('\0');
    return out;
}

static int __cdecl HookWrapDraw(char* text, int* fontWrapper, int x0, int y0, int x1, int y1, int align, uint32_t color, int startLine) {
    auto orig = reinterpret_cast<WrapDrawFn>(gWrapDrawTrampoline);
    if (!text || !fontWrapper || !*fontWrapper) return orig(text, fontWrapper, x0, y0, x1, y1, align, color, startLine);
    bool hasMarker = (strncmp(text, "\x01THAI\x01", 6) == 0);
    if (!hasMarker && !contains_thai_utf8(text)) return orig(text, fontWrapper, x0, y0, x1, y1, align, color, startLine);
    float scaleX = *reinterpret_cast<const float*>(&fontWrapper[1]);
    if (scaleX <= 0.0f) scaleX = 1.0f;
    int maxWidth = static_cast<int>(static_cast<float>(x1 - x0) / scaleX);
    static int sWrapLogCount = 0;
    if (sWrapLogCount < 20) {
        ++sWrapLogCount;
        char msg[256];
        snprintf(msg, sizeof(msg), "WrapDraw#%d: x0=%d x1=%d scaleX=%.3f maxW=%d len=%zu align=%d start=%d",
                 sWrapLogCount, x0, x1, scaleX, maxWidth, strlen(text), align, startLine);
        log_line(msg);
    }
    if (maxWidth <= 0) return orig(text, fontWrapper, x0, y0, x1, y1, align, color, startLine);
    std::vector<char> wrapped = wrap_thai_for_box(static_cast<uintptr_t>(*fontWrapper), text, maxWidth);
    return orig(wrapped.data(), fontWrapper, x0, y0, x1, y1, align, color, startLine);
}

static int __cdecl HookWrapDraw2D(char* text, uintptr_t fontThis, int x0, int y0, int x1, int y1, int align, uint32_t color, int startLine, int p10, int p11) {
    auto orig = reinterpret_cast<WrapDraw2DFn>(gWrapDraw2DTrampoline);
    if (!text || !fontThis) return orig(text, fontThis, x0, y0, x1, y1, align, color, startLine, p10, p11);
    bool hasMarker = (strncmp(text, "\x01THAI\x01", 6) == 0);
    if (!hasMarker && !contains_thai_utf8(text)) return orig(text, fontThis, x0, y0, x1, y1, align, color, startLine, p10, p11);
    int maxWidth = x1 - x0;
    static int sWrap2DLogCount = 0;
    if (sWrap2DLogCount < 20) {
        ++sWrap2DLogCount;
        char msg[256];
        snprintf(msg, sizeof(msg), "WrapDraw2D#%d: x0=%d x1=%d maxW=%d len=%zu align=%d start=%d",
                 sWrap2DLogCount, x0, x1, maxWidth, strlen(text), align, startLine);
        log_line(msg);
    }
    if (maxWidth <= 0) return orig(text, fontThis, x0, y0, x1, y1, align, color, startLine, p10, p11);
    std::vector<char> wrapped = wrap_thai_for_box(fontThis, text, maxWidth);
    return orig(wrapped.data(), fontThis, x0, y0, x1, y1, align, color, startLine, p10, p11);
}

static void __cdecl HookUiWrapDraw(char* text, uintptr_t fontObj, int x0, int y0, int boxW, int boxH, int colorMode, int align, int p9, float scale, int startLine) {
    auto orig = reinterpret_cast<UiWrapDrawFn>(gUiWrapDrawTrampoline);
    if (!text || !fontObj || !x0 || !y0) { orig(text, fontObj, x0, y0, boxW, boxH, colorMode, align, p9, scale, startLine); return; }
    uintptr_t fontThis = *reinterpret_cast<const uintptr_t*>(fontObj + 0x108);
    if (!fontThis) { orig(text, fontObj, x0, y0, boxW, boxH, colorMode, align, p9, scale, startLine); return; }
    bool hasMarker = (strncmp(text, "\x01THAI\x01", 6) == 0);
    if (!hasMarker && !contains_thai_utf8(text)) { orig(text, fontObj, x0, y0, boxW, boxH, colorMode, align, p9, scale, startLine); return; }
    if (boxW <= 0) { orig(text, fontObj, x0, y0, boxW, boxH, colorMode, align, p9, scale, startLine); return; }
    float sc = (scale > 0.0f) ? scale : 1.0f;
    int maxWidth = static_cast<int>(static_cast<float>(boxW) / sc);
    if (maxWidth <= 0) { orig(text, fontObj, x0, y0, boxW, boxH, colorMode, align, p9, scale, startLine); return; }
    std::vector<char> wrapped = wrap_thai_for_box(fontThis, text, maxWidth, false);
    orig(wrapped.data(), fontObj, x0, y0, 0x10000, boxH, colorMode, align, p9, scale, startLine);
}

static DWORD WINAPI install_thread(void*) {
    Sleep(100);
    log_line("Thai runtime loaded; reading glyph map");
    if (!load_map()) { log_line("ERROR: glyph map load failed"); return 0; }
    log_line("Glyph map loaded");
    InitializeCriticalSection(&gPatchLock); gLockReady = true;
    wchar_t disableHooks[8]{};
    if (GetEnvironmentVariableW(L"THAI_DISABLE_HOOKS", disableHooks, 8) > 0 && disableHooks[0] == L'1') {
        log_line("Renderer hooks disabled by THAI_DISABLE_HOOKS");
        return 0;
    }
    wchar_t hookMask[16] = L"DEMC";
    DWORD hookMaskSize = GetEnvironmentVariableW(L"THAI_HOOK_MASK", hookMask, 16);
    if (!hookMaskSize || hookMaskSize >= 16) wcscpy_s(hookMask, L"DEMC");
    auto enabled = [&](wchar_t c) { return wcschr(hookMask, c) != nullptr; };
    wchar_t disableGlyph[8]{};
    gEnableGlyphPatch = !(GetEnvironmentVariableW(L"THAI_DISABLE_GLYPH_PATCH", disableGlyph, 8) > 0 && disableGlyph[0] == L'1');
    uintptr_t base = reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    uintptr_t draw = base + (0x005adfc0 - 0x00400000);
    uintptr_t meas = base + (0x005adb60 - 0x00400000);
    gMeasureAddr = meas;
    uintptr_t mchar = base + (0x005adcb1 - 0x00400000);
    uintptr_t dchar = base + (0x005ae2f0 - 0x00400000);
    uintptr_t wdraw = base + (0x004f7120 - 0x00400000);
    uintptr_t wdraw2d = base + (0x004f7360 - 0x00400000);
    uintptr_t uiwdraw = base + (0x00573e50 - 0x00400000);
    const uint8_t drawBytes[] = {0x55,0x8b,0xec,0x83,0xe4,0xf8};
    const uint8_t measBytes[] = {0x83,0xec,0x20,0x53,0x55};
    const uint8_t mcharBytes[] = {0x8b,0x44,0x24,0x18,0x25,0xff,0x00,0x00,0x00,0x8d,0x14,0x80};
    const uint8_t dcharBytes[] = {0x8b,0x84,0x24,0x80,0x00,0x00,0x00,0x8b,0x54,0x24,0x14};
    const uint8_t wdrawBytes[] = {0x55,0x8b,0xec,0x83,0xec,0x40};
    const uint8_t wdraw2dBytes[] = {0x55,0x8b,0xec,0x83,0xec,0x44};
    const uint8_t uiwdrawBytes[] = {0x83,0xec,0x20,0x8b,0x44,0x24,0x30};
    gDrawTrampoline = make_trampoline(draw, drawBytes, sizeof(drawBytes));
    gMeasureEntryTrampoline = make_trampoline(meas, measBytes, sizeof(measBytes));
    gWrapDrawTrampoline = make_trampoline(wdraw, wdrawBytes, sizeof(wdrawBytes));
    gWrapDraw2DTrampoline = make_trampoline(wdraw2d, wdraw2dBytes, sizeof(wdraw2dBytes));
    gUiWrapDrawTrampoline = make_trampoline(uiwdraw, uiwdrawBytes, sizeof(uiwdrawBytes));
    gDrawContinue = dchar + sizeof(dcharBytes);
    gMeasureMidContinue = mchar + sizeof(mcharBytes);
    if (!gDrawTrampoline || !gMeasureEntryTrampoline) { log_line("ERROR: executable signature mismatch"); return 0; }
    if (memcmp(reinterpret_cast<void*>(mchar), mcharBytes, sizeof(mcharBytes)) != 0 ||
        memcmp(reinterpret_cast<void*>(dchar), dcharBytes, sizeof(dcharBytes)) != 0) {
        log_line("ERROR: glyph-hook signature mismatch"); return 0;
    }
    if (enabled(L'D') && !install_jump(draw, HookDraw, sizeof(drawBytes))) { log_line("ERROR: draw hook install failed"); return 0; }
    if (enabled(L'E') && !install_jump(meas, HookMeasureEntry, sizeof(measBytes))) { log_line("ERROR: measure entry hook install failed"); return 0; }
    if (enabled(L'M') && !install_jump(mchar, HookMeasureChar, sizeof(mcharBytes))) { log_line("ERROR: measure glyph hook install failed"); return 0; }
    if (enabled(L'C') && !install_jump(dchar, HookDrawChar, sizeof(dcharBytes))) { log_line("ERROR: draw glyph hook install failed"); return 0; }
    if (gWrapDrawTrampoline && install_jump(wdraw, HookWrapDraw, sizeof(wdrawBytes))) log_line("WrapDraw hook installed");
    else log_line("WARN: WrapDraw hook NOT installed");
    if (gWrapDraw2DTrampoline && install_jump(wdraw2d, HookWrapDraw2D, sizeof(wdraw2dBytes))) log_line("WrapDraw2D hook installed");
    else log_line("WARN: WrapDraw2D hook NOT installed");
    if (gUiWrapDrawTrampoline && install_jump(uiwdraw, HookUiWrapDraw, sizeof(uiwdrawBytes))) log_line("UiWrapDraw hook installed");
    else log_line("WARN: UiWrapDraw hook NOT installed");
    log_line("Renderer hook mask installed");
    return 0;
}

typedef void* (WINAPI *Direct3DCreate8Fn)(UINT);
extern "C" __declspec(dllexport) void* WINAPI Direct3DCreate8(UINT sdk) {
    if (!gRealD3D8) {
        gRealD3D8 = LoadLibraryW(L"wrappers\\dgVoodoo\\D3D8.dll");
        if (gRealD3D8) gRealCreate8 = GetProcAddress(gRealD3D8, "Direct3DCreate8");
    }
    if (!gRealCreate8) { log_line("ERROR: dgVoodoo D3D8 forwarder not found"); return nullptr; }
    return reinterpret_cast<Direct3DCreate8Fn>(gRealCreate8)(sdk);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        gDrawTls = TlsAlloc();
        gMeasureTls = TlsAlloc();
        HANDLE t = CreateThread(nullptr, 0, install_thread, nullptr, 0, nullptr);
        if (t) CloseHandle(t);
    } else if (reason == DLL_PROCESS_DETACH && gLockReady) {
        DeleteCriticalSection(&gPatchLock);
        if (gDrawTls != TLS_OUT_OF_INDEXES) TlsFree(gDrawTls);
        if (gMeasureTls != TLS_OUT_OF_INDEXES) TlsFree(gMeasureTls);
    }
    return TRUE;
}
