import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.argv[2] || "http://127.0.0.1:8501";
const sourceText = "# Chapter 1\nnight radio 电台在雨夜响起，仓库钥匙仍在青瓷碗底。\n\n这一段保留可验证的 Unicode 偏移。\n";
const markdownText = "## Chapter 2\nnight radio 电台再次响起，林澄核对账本。\n\n第二个显式 Markdown 来源。\n";
const externalRequests = [];

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

async function pageText(page) {
  let text = await page.locator("body").innerText();
  const frames = page.locator('[data-testid="stDataFrame"] iframe');
  for (let index = 0; index < await frames.count(); index += 1) {
    try {
      text += "\n" + await frames.nth(index).contentFrame().locator("body").innerText();
    } catch {
      // The dataframe can be between reruns while its iframe is replaced.
    }
  }
  return text;
}

async function waitForText(page, expected, timeout = 45000) {
  const deadline = Date.now() + timeout;
  let last = "";
  while (Date.now() < deadline) {
    last = await pageText(page);
    if (typeof expected === "string" ? last.includes(expected) : expected.test(last)) {
      return last;
    }
    await page.waitForTimeout(250);
  }
  throw new Error("Timed out waiting for " + expected + "\n" + last.slice(-4000));
}

async function waitForCount(locator, expected, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await locator.count() === expected) return;
    await locator.page().waitForTimeout(200);
  }
  throw new Error("Timed out waiting for count " + expected);
}

async function downloadJson(page, label) {
  const downloadPromise = page.waitForEvent("download");
  await page.getByText(label, { exact: true }).click();
  const download = await downloadPromise;
  const filePath = await download.path();
  assert(filePath, "download must have a completed temporary path");
  const bytes = await fs.readFile(filePath);
  assert(bytes.length > 0, label + " bytes must be non-empty");
  return { bytes, payload: JSON.parse(bytes.toString("utf8")) };
}

async function filesUnder(directory) {
  const result = [];
  try {
    for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
      const child = path.join(directory, entry.name);
      if (entry.isDirectory()) result.push(...await filesUnder(child));
      else result.push(child);
    }
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  return result;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ acceptDownloads: true });
    page.on("request", request => {
      const hostname = new URL(request.url()).hostname;
      if (hostname !== "127.0.0.1" && hostname !== "localhost") {
        externalRequests.push(request.url());
      }
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await page.getByRole("tab", { name: /本地证据/ }).click();

    const fileInputs = page.locator('[data-testid="stFileUploader"] input[type="file"]');
    const fallbackInputs = page.locator('input[type="file"]');
    const inputCount = await fileInputs.count();
    const evidenceInput = inputCount ? fileInputs.last() : fallbackInputs.last();
    assert(await evidenceInput.count() === 1, "evidence file input must exist");
    await evidenceInput.setInputFiles([
      { name: "source.txt", mimeType: "text/plain", buffer: Buffer.from(sourceText, "utf8") },
      { name: "source.md", mimeType: "text/markdown", buffer: Buffer.from(markdownText, "utf8") },
    ]);

    await page.getByLabel("查询词 / query", { exact: true }).fill("night 电台");
    await page.getByLabel("返回数量 top_n", { exact: true }).fill("2");
    assert.equal(
      await page.getByLabel("返回数量 top_n", { exact: true }).getAttribute("max"),
      "20",
    );
    await page.getByRole("button", { name: "查询本地参考证据", exact: true }).click();
    await waitForText(page, "本地证据查询完成：");

    const evidenceDownload = await downloadJson(page, "下载本次证据 JSON");
    const evidence = evidenceDownload.payload;
    assert.equal(evidence.schema, "novel-reference-evidence-v1");
    assert.equal(evidence.query, "night 电台");
    assert.equal(evidence.parameters.top_n, 2);
    assert(evidence.matches.length > 0 && evidence.matches.length <= 2);
    const evidenceMatch = evidence.matches.find(match => match.source_filename === "source.txt");
    assert(evidenceMatch, "source.txt must be selected by the mixed query");
    const sourceManifest = evidence.sources.find(source => source.filename === "source.txt");
    assert(sourceManifest, "source.txt manifest must be present");
    assert.equal(sourceManifest.raw_source_sha256, sha256(Buffer.from(sourceText, "utf8")));
    assert.equal(evidenceMatch.raw_source_sha256, sourceManifest.raw_source_sha256);
    assert.equal(evidenceMatch.extracted_text_sha256, sourceManifest.extracted_text_sha256);
    assert.equal(evidenceMatch.chapter, "Chapter 1");
    assert(evidenceMatch.end > evidenceMatch.start);
    assert.equal(sourceText.slice(evidenceMatch.start, evidenceMatch.end), evidenceMatch.excerpt);
    assert.equal(evidenceMatch.offset_basis, "sanitized-extracted-unicode-codepoints");
    assert(evidenceMatch.id && evidenceMatch.id.length === 64);
    const visibleEvidence = await waitForText(page, evidenceMatch.id);
    for (const value of [
      evidenceMatch.source_filename,
      evidenceMatch.raw_source_sha256,
      evidenceMatch.extracted_text_sha256,
      evidenceMatch.id,
      evidenceMatch.start + ":" + evidenceMatch.end,
    ]) {
      assert(visibleEvidence.includes(String(value)), "visible evidence result missing " + value);
    }

    const draft = "night radio 电台在雨夜响起";
    const draftField = page.getByLabel("明确粘贴稿件片段（仅当前会话）", { exact: true });
    assert.equal(await draftField.getAttribute("maxlength"), "2048");
    await draftField.fill(draft);
    await page.getByRole("checkbox", { name: /选择证据 1:/ }).first().check();
    await page.getByRole("button", { name: "检查措辞相近度", exact: true }).click();
    await waitForText(page, "措辞相近检查完成：");

    const wordingDownload = await downloadJson(page, "下载本次措辞检查 JSON");
    const wording = wordingDownload.payload;
    assert.equal(wording.schema, "novel-reference-wording-check-v1");
    assert.equal(wording.project, "MyNovel");
    assert.equal(wording.evidence_query, "night 电台");
    assert.equal(wording.draft_sha256, sha256(draft));
    assert.equal(wording.selected_match_ids.length, 1);
    assert.equal(wording.selected_match_ids[0], evidenceMatch.id);
    assert.equal(wording.parameters.max_draft_chars, 2048);
    assert.equal(wording.parameters.max_matches, 20);
    assert.equal(wording.parameters.max_comparisons, 20);
    assert.equal(wording.metric.name, "normalized_levenshtein_similarity");
    assert.equal(wording.metric.implementation, "novel_ai.rapidfuzz_similarity.normalized_similarity");
    assert.equal(wording.metric.upstream_commit, "db6e504539a9c895180b266a06b36a32cb6029ee");
    assert.equal(wording.metric.license, "MIT");
    const wordingMatch = wording.matches[0];
    assert.equal(wordingMatch.stable_id, evidenceMatch.id);
    assert.equal(wordingMatch.source_filename, evidenceMatch.source_filename);
    assert.equal(wordingMatch.start, evidenceMatch.start);
    assert.equal(wordingMatch.end, evidenceMatch.end);
    assert.equal(wordingMatch.raw_source_sha256, evidenceMatch.raw_source_sha256);
    assert.equal(wordingMatch.extracted_text_sha256, evidenceMatch.extracted_text_sha256);
    assert(Number.isFinite(wordingMatch.similarity));
    assert(wordingMatch.similarity > 0 && wordingMatch.similarity < 1);
    assert(!Object.prototype.hasOwnProperty.call(wordingMatch, "bounded_excerpt"));
    assert(!JSON.stringify(wording).includes(draft));

    const visibleWording = await waitForText(page, evidenceMatch.id);
    assert.equal(await draftField.inputValue(), draft);
    for (const value of [
      wording.metric.name,
      wording.draft_sha256,
      wordingMatch.stable_id,
      wordingMatch.raw_source_sha256,
      wordingMatch.extracted_text_sha256,
      wordingMatch.start + ":" + wordingMatch.end,
      String(wordingMatch.similarity),
    ]) {
      assert(visibleWording.includes(String(value)), "visible wording result missing " + value);
    }

    await draftField.fill("编辑后的新片段");
    await waitForCount(page.getByText("下载本次措辞检查 JSON", { exact: true }), 0);
    await page.getByRole("checkbox", { name: /选择证据 1:/ }).first().uncheck();
    await page.getByRole("button", { name: "检查措辞相近度", exact: true }).click();
    await waitForText(page, "措辞相近检查未完成：");
    await waitForCount(page.getByText("下载本次措辞检查 JSON", { exact: true }), 0);

    await page.getByRole("checkbox", { name: /选择证据 1:/ }).first().check();
    await draftField.fill(draft);
    await page.getByRole("button", { name: "检查措辞相近度", exact: true }).click();
    await waitForText(page, "措辞相近检查完成：");
    const repeatedDownload = await downloadJson(page, "下载本次措辞检查 JSON");
    assert.equal(Buffer.compare(wordingDownload.bytes, repeatedDownload.bytes), 0);

    await page.getByRole("button", { name: "检查措辞相近度", exact: true }).click();
    await waitForText(page, "措辞相近检查完成：");
    const secondRepeat = await downloadJson(page, "下载本次措辞检查 JSON");
    assert.equal(Buffer.compare(repeatedDownload.bytes, secondRepeat.bytes), 0);

    const projectField = page.getByLabel("当前项目", { exact: true });
    await projectField.fill("BrowserOtherBook");
    await waitForCount(page.getByText("下载本次措辞检查 JSON", { exact: true }), 0);
    await waitForCount(page.getByText("下载本次证据 JSON", { exact: true }), 0);
    assert.equal((await pageText(page)).includes(evidenceMatch.id), false);

    assert.deepEqual(externalRequests, []);
    for (const filePath of await filesUnder(path.resolve("data"))) {
      const body = await fs.readFile(filePath);
      assert(!body.includes(Buffer.from("night radio", "utf8")), "source body must not be persisted");
      assert(!body.includes(Buffer.from("编辑后的新片段", "utf8")), "draft body must not be persisted");
    }

    console.log(JSON.stringify({
      evidence_download_bytes: evidenceDownload.bytes.length,
      wording_download_bytes: wordingDownload.bytes.length,
      repeated_download_bytes: repeatedDownload.bytes.length,
      evidence_matches: evidence.matches.length,
      wording_matches: wording.matches.length,
      external_requests: externalRequests.length,
    }));
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
