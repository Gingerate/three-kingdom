const { chromium } = require('C:\\Users\\jinli\\AppData\\Roaming\\npm\\node_modules\\@playwright\\cli\\node_modules\\playwright-core');
const fs = require('fs');
const path = require('path');

// 截图配置
const CONFIG = {
  baseUrl: 'http://localhost:5173',
  outputDir: path.join(__dirname, '..', 'screenshots'),
  viewport: { width: 1440, height: 900 },
  pages: [
    {
      name: 'chat',
      url: '/chat',
      waitFor: 'text=智能问答',
      description: '智能问答页面'
    },
    {
      name: 'wiki',
      url: '/wiki',
      waitFor: 'text=知识沉淀',
      description: '知识沉淀页面'
    },
    {
      name: 'graph',
      url: '/graph',
      waitFor: 'text=知识图谱',
      description: '知识图谱页面'
    },
    {
      name: 'data',
      url: '/data',
      waitFor: 'text=数据管理',
      description: '数据管理页面'
    }
  ]
};

async function takeScreenshots() {
  // 创建输出目录
  if (!fs.existsSync(CONFIG.outputDir)) {
    fs.mkdirSync(CONFIG.outputDir, { recursive: true });
  }

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Users\\jinli\\AppData\\Local\\ms-playwright\\chromium-1223\\chrome-win64\\chrome.exe'
  });
  const context = await browser.newContext({
    viewport: CONFIG.viewport,
    locale: 'zh-CN'
  });

  console.log('🎬 开始截图...\n');

  for (const pageConfig of CONFIG.pages) {
    try {
      const page = await context.newPage();
      const url = `${CONFIG.baseUrl}${pageConfig.url}`;

      console.log(`📸 正在截图: ${pageConfig.description}`);
      console.log(`   URL: ${url}`);

      // 访问页面
      await page.goto(url, { waitUntil: 'networkidle' });

      // 等待特定内容加载
      if (pageConfig.waitFor) {
        await page.waitForSelector(pageConfig.waitFor, { timeout: 10000 }).catch(() => {
          console.log(`   ⚠️  等待超时，继续截图...`);
        });
      }

      // 等待动画完成
      await page.waitForTimeout(2000);

      // 截图
      const screenshotPath = path.join(CONFIG.outputDir, `${pageConfig.name}.png`);
      await page.screenshot({
        path: screenshotPath,
        fullPage: false
      });

      console.log(`   ✅ 已保存: ${screenshotPath}\n`);

      await page.close();
    } catch (error) {
      console.error(`   ❌ 截图失败: ${error.message}\n`);
    }
  }

  await browser.close();

  console.log('🎉 截图完成！');
  console.log(`📁 截图目录: ${CONFIG.outputDir}`);
}

// 运行截图
takeScreenshots().catch(console.error);
