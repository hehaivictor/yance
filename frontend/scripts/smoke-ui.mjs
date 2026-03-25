import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const outputDir = path.resolve(__dirname, "../../output/playwright");
const urlArg = process.argv.find((item) => item.startsWith("--url="));
const baseUrl = urlArg?.slice("--url=".length) || process.env.UI_SMOKE_BASE_URL || "http://127.0.0.1:3100";
const screenshotPath = path.join(outputDir, "yance-ui-smoke.png");
const reportPath = path.join(outputDir, "yance-ui-smoke.json");

const report = {
  baseUrl,
  checkedAt: new Date().toISOString(),
  steps: [],
};

function pushStep(name, status, detail, durationMs) {
  report.steps.push({ name, status, detail, durationMs });
}

async function runStep(name, fn) {
  const startedAt = Date.now();
  try {
    await fn();
    pushStep(name, "passed", "", Date.now() - startedAt);
  } catch (error) {
    pushStep(
      name,
      "failed",
      error instanceof Error ? error.message : "未知错误",
      Date.now() - startedAt,
    );
    throw error;
  }
}

async function assertVisible(locator, description) {
  if (!(await locator.first().isVisible())) {
    throw new Error(`未找到：${description}`);
  }
}

async function clickNav(page, label, expectedText) {
  const button = page.locator("nav button").filter({ hasText: new RegExp(`^${label}`) }).first();
  await assertVisible(button, `${label} 导航按钮`);
  await button.click();
  await page.waitForTimeout(180);
  await assertVisible(page.getByText(expectedText).first(), `${label} 区域特征文案`);
}

async function main() {
  await mkdir(outputDir, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
  });

  try {
    const page = await browser.newPage({
      viewport: { width: 1512, height: 1100 },
      deviceScaleFactor: 1,
    });

    await runStep("打开页面", async () => {
      await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page.waitForTimeout(1200);
      await assertVisible(page.getByText("研策 Yance").first(), "品牌标题");
      await assertVisible(page.getByText("让开题更成体系").first(), "品牌 Slogan");
    });

    await runStep("检查主流程导航", async () => {
      await clickNav(page, "基础信息", "先填导师侧、学生侧和上传资料");
      await clickNav(page, "推荐选题", "必要时先访谈，再比较候选题");
      await clickNav(page, "开题生成", "生成开题报告");
    });

    await runStep("检查创建入口", async () => {
      await assertVisible(page.getByText("创建项目").first(), "创建项目入口");
      await assertVisible(page.getByLabel("项目名称").first(), "项目名称输入框");
      await assertVisible(page.getByLabel("学校").first(), "学校选择框");
    });

    await runStep("输出截图", async () => {
      await page.screenshot({ path: screenshotPath, fullPage: true });
    });
  } finally {
    await browser.close();
  }
}

try {
  await main();
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(`[smoke] 检查通过：${baseUrl}`);
  console.log(`[smoke] 截图：${screenshotPath}`);
  console.log(`[smoke] 报告：${reportPath}`);
} catch (error) {
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.error(error instanceof Error ? error.message : "UI smoke 失败");
  console.error(`[smoke] 报告：${reportPath}`);
  process.exitCode = 1;
}
