import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = path.resolve(process.argv[2]);
const previewDir = path.resolve(process.argv[3]);
await fs.mkdir(previewDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 8000,
  tableMaxRows: 8,
  tableMaxCols: 12,
});
console.log(overview.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "operator workbook formula error scan",
});
console.log(errors.ndjson);
if (!errors.ndjson.includes("Cell search matched 0 entries.")) {
  throw new Error("WORKBOOK_FORMULA_ERROR_SCAN_NOT_CLEAN");
}
const sheetNames = [
  "Run Control",
  "Evidence Paste",
  "Portfolio",
  "QA",
  "Upload",
  "Exposure",
  "Review Evidence",
  "Artifacts",
];
for (const sheetName of sheetNames) {
  const preview = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  const safeName = sheetName.toLowerCase().replaceAll(" ", "_");
  await fs.writeFile(
    path.join(previewDir, `${safeName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}
console.log(`WORKBOOK_VERIFY=PASS SHEETS_RENDERED=${sheetNames.length}`);
