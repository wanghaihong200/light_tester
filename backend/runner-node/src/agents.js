// runner-node/src/agents.js
// 三端 runtime 工厂:契约 { page?, agent, launch?, screenshot(), reportFile(), close() }。
// web=Playwright(复用 %LOCALAPPDATA%/ms-playwright 的 chromium);android=adb;harmony=hdc。

export async function createRuntime(job) {
  if (job.target === 'web') return createWebRuntime(job);
  if (job.target === 'android') return createAndroidRuntime(job);
  if (job.target === 'harmony') return createHarmonyRuntime(job);
  throw new Error(`未知 target: ${job.target}`);
}

async function createWebRuntime(job) {
  const { chromium } = await import('playwright');
  const { PlaywrightAgent } = await import('@midscene/web/playwright');
  const browser = await chromium.launch({ headless: job.mode !== 'headed' });
  const context = await browser.newContext(job.storage_state ? { storageState: job.storage_state } : {});
  const page = context.pages()[0] || (await context.newPage());
  const agent = new PlaywrightAgent(page);
  if (job.start_url) await page.goto(job.start_url, { waitUntil: 'domcontentloaded' }).catch(() => {});
  let looping = true;
  const frameLoop = (async () => {
    while (looping) {
      try {
        process.stdout.write(JSON.stringify({ type: 'frame',
          data: (await page.screenshot({ type: 'jpeg', quality: 55 })).toString('base64'),
          step_index: -1 }) + '\n');
      } catch {}
      await new Promise((r) => setTimeout(r, 1000));
    }
  })();
  return {
    page, agent,
    async screenshot() { return page.screenshot({ type: 'jpeg', quality: 70 }); },
    reportFile() { return agent.reportFile || ''; },
    async close() { looping = false; await frameLoop.catch(() => {}); await agent.destroy?.(); await browser.close(); },
  };
}

async function createAndroidRuntime(job) {
  const { AndroidAgent, AndroidDevice, getConnectedDevices } = await import('@midscene/android');
  const devices = await getConnectedDevices();
  if (!devices.length) throw new Error('无在线 Android 设备(adb devices 为空)');
  const device = new AndroidDevice(devices[0].udid);
  await device.connect();
  const agent = new AndroidAgent(device, {});
  return {
    agent,
    async launch() { if (job.launch_target) await agent.launch(job.launch_target); },
    async screenshot() { try { return await device.screenshot(); } catch { return null; } },
    reportFile() { return agent.reportFile || ''; },
    async close() { await agent.destroy?.(); },
  };
}

async function createHarmonyRuntime(job) {
  const { HarmonyAgent, HarmonyDevice, getConnectedDevices } = await import('@midscene/harmony');
  const devices = await getConnectedDevices();
  if (!devices.length) throw new Error('无在线鸿蒙设备(hdc list targets 为空)');
  const device = new HarmonyDevice(devices[0].deviceId, {});
  await device.connect();
  const agent = new HarmonyAgent(device, {});
  return {
    agent,
    async launch() { if (job.launch_target) await agent.launch(job.launch_target); },
    async screenshot() { try { return await device.screenshot(); } catch { return null; } },
    reportFile() { return agent.reportFile || ''; },
    async close() { await agent.destroy?.(); },
  };
}
