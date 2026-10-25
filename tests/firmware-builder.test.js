// Test harness for the firmware builder's dump-analysis logic
// (docs/download.html). It extracts the inline <script> block, evaluates it
// in a Node context, and exercises it against a synthetic 40 MB GamiJa-style
// stock dump:
//   - script.bin   at byte 20488192 (issue #99's GamiJa offset, length 164)
//   - boot0 marker at byte 8192, u-boot marker at byte 49152
//   - stock kernel "ANDROID!" boot image header injected at sector 24000
//
// Run from anywhere:  node tests/firmware-builder.test.js

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const downloadHtml = path.join(__dirname, "..", "docs", "download.html");
const html = fs.readFileSync(downloadHtml, "utf8");

// Extract the inline script block the same way the browser would load it.
const match = html.match(/^<script>$[\s\S]*?^<\/script>$/m);
if (!match) {
  console.error("No inline <script> block found in docs/download.html");
  process.exit(1);
}
const script = match[0].replace(/^<script>$/m, "").replace(/^<\/script>$/m, "");

const ctx = { console, Blob, TextDecoder, document: { addEventListener() {} } };
vm.createContext(ctx);
vm.runInContext(
  script +
    "\n; globalThis.T = { computeScriptBinLength, isScriptBinPossibility, findScriptBinCandidates, describePartitionTable, scanBootMarkers, viewSigMatches, CONFIG, SCRIPT_BIN };",
  ctx
);
const T = ctx.T;

// ---- Build a synthetic 40MB "GamiJa-style" dump ----
const SIZE = 40 * 1024 * 1024;
const buf = Buffer.alloc(SIZE);

// MBR signature + one FAT32 partition entry
buf.writeUInt8(0x55, 510); buf.writeUInt8(0xaa, 511);
buf.writeUInt8(0x0b, 446 + 4);
buf.writeUInt32LE(20488192 / 512, 446 + 8);

// boot0 marker at 8 KiB, u-boot-ish eGON at 0xC000 sector-aligned
buf.write("eGON.BT0", 8192, "ascii");
buf.write("eGON", 49152, "ascii");

// A stock kernel image that the GamiJa bootloader would load: the
// resolution logic must find this ("ANDROID!" boot image header).
const KSEC = 24000;                 // sector 24000 -> byte 12288000 (11.7 MiB)
buf.write("ANDROID!", KSEC * 512, "ascii");

// script.bin at the GamiJa offset (20488192), per issue #99 maintainer notes
const SB = 20488192;
const header = Buffer.alloc(16);
header.writeUInt32LE(2, 0);        // 2 sections
header.writeUInt32LE(164, 4);      // total size
header.write("000001", 8, "ascii"); // version bytes
header.copy(buf, SB);

const section = (name, entryCount, tableOffsetWords) => {
  const s = Buffer.alloc(40);
  s.write(name, 0, "ascii", 32);
  s.writeInt32LE(entryCount, 32);
  s.writeInt32LE(tableOffsetWords, 36);
  return s;
};
section("target", 1, 24).copy(buf, SB + 16);
section("platform", 0, 34).copy(buf, SB + 16 + 40);

const entry = (name, dataOffsetWords, wordCount) => {
  const e = Buffer.alloc(40);
  e.write(name, 0, "ascii", 32);
  e.writeInt32LE(dataOffsetWords, 32);
  e.writeUInt32LE(wordCount, 36);
  return e;
};
entry("testkey", 40, 1).copy(buf, SB + 16 + 80); // entry table for section 0 at word 24
buf.writeUInt32LE(0x12345678, SB + 164); // entry data

const file = {
  size: SIZE,
  slice(start, end) { return new Blob([buf.subarray(start, end)]); }
};

// ---- Tests ----
(async () => {
  let failures = 0;
  const ok = (name, cond) => { console.log((cond ? "PASS" : "FAIL") + ": " + name); if (!cond) failures++; };

  // 0. Layout table sanity
  ok("ga36mb kernel sector == 172032", T.CONFIG.LAYOUTS.ga36mb.kernelSector === 172032);
  ok("gaminja script.bin offset == 20488192", T.CONFIG.LAYOUTS.gaminja.scriptBinOffsets[0] === 20488192);
  ok("gaminja kernel sector unmeasured (null)", T.CONFIG.LAYOUTS.gaminja.kernelSector === null);

  // 1. Direct parse at the GamiJa offset
  const region = buf.subarray(SB, SB + T.CONFIG.SCRIPT_BIN_MAX_LENGTH);
  const length = T.computeScriptBinLength(new DataView(region.buffer, region.byteOffset), 0);
  ok("script.bin parses at GamiJa offset with length 164", length === 164);

  // 2a. GA36 offset is garbage in this layout -> must throw
  const ga36 = buf.subarray(20340736, 20340736 + T.CONFIG.SCRIPT_BIN_MAX_LENGTH);
  let threw = false;
  try { T.computeScriptBinLength(new DataView(ga36.buffer, ga36.byteOffset), 0); } catch { threw = true; }
  ok("GA36 offset parse throws on this layout", threw);

  // 2b. All-zero region must also throw (not parse as an "empty" script.bin)
  const zeros = Buffer.alloc(1024);
  threw = false;
  try { T.computeScriptBinLength(new DataView(zeros.buffer), 0); } catch { threw = true; }
  ok("all-zero region parse throws", threw);

  // 3. Scan finds exactly the GamiJa candidate
  const cands = await T.findScriptBinCandidates(file, SIZE);
  ok("scan returns 1 candidate", cands.length === 1);
  ok("scan candidate offset == 20488192", cands.length === 1 && cands[0].offset === 20488192);
  ok("scan candidate length == 164", cands.length === 1 && cands[0].length === 164);

  // 4. Boot markers + kernel-offset candidates
  const scan = await T.scanBootMarkers(file, SIZE);
  console.log("markers:", scan.lines);
  ok("markers line detect eGON.BT0", scan.lines.some(m => m.startsWith("boot0 (eGON.BT0): 1 hit(s) at bytes [8192]")));
  ok("markers line detect eGON at 8192 and 49152",
     scan.lines.some(m => m.startsWith("boot1/u-boot (eGON): 2 hit(s) at bytes [8192, 49152]")));
  ok("ANDROID! header found at injected kernel sector",
     scan.androidOffsets.length === 1 && scan.androidOffsets[0] === KSEC * 512);
  const inBounds = scan.androidOffsets.filter(o => o / T.CONFIG.SECTOR >= 1025 && o / T.CONFIG.SECTOR <= 262143);
  ok("in-bounds resolution -> sector 24000", inBounds.length === 1 && inBounds[0] / T.CONFIG.SECTOR === 24000);

  // 5. Partition table
  const parts = await T.describePartitionTable(file);
  console.log("parts:", parts);
  ok("MBR signature reported", parts.some(l => l.startsWith("MBR: 0x55AA")));
  ok("FAT32 partition entry parsed", parts.some(l => l.includes("type=0x0b")));
  ok("no GPT reported", !parts.some(l => l.startsWith("GPT:")));

  console.log(failures === 0 ? "\nALL TESTS PASSED" : `\n${failures} FAILURES`);
  process.exit(failures === 0 ? 0 : 1);
})();
