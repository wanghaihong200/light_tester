// runner-node/src/main.js
// 用法:node src/main.js <job.json>;stdout NDJSON 事件;主循环 fail-fast 与 Python 路径一致。
import { writeFileSync } from 'node:fs';
import { createEmitter, readJob } from './protocol.js';
import { runStep } from './steps.js';

export async function runJob(job, { createRuntime, emit }) {
  emit({ type: 'step_start', index: -1 }); // 首帧占位(与 Python 路径一致)
  const rt = await createRuntime(job);
  const vars = { ...job.variables };
  const results = [];
  let failed = 0;
  const t0 = Date.now();
  try {
    if (job.launch_target) await rt.launch?.();
    for (let i = 0; i < job.steps.length; i++) {
      const step = job.steps[i];
      emit({ type: 'step_start', index: i });
      const pre = await rt.screenshot();
      if (pre) emit({ type: 'frame', data: pre.toString('base64'), step_index: i });
      let r;
      try {
        r = await runStep({ page: rt.page, agent: rt.agent, step, vars });
      } catch (e) {
        r = { status: 'failed', error: String(e?.message || e).split('\n')[0].slice(0, 300) };
      }
      const status = r?.status === 'passed' ? 'passed' : 'failed';
      const shotName = `step_${i}_${status}.jpg`;
      try {
        const shot = await rt.screenshot();
        if (shot) writeFileSync(`${job.out_dir}/${shotName}`, shot);
      } catch {}
      results.push({ index: i, step_id: step.id, action: step.action, status,
                     error: r?.error || null, screenshot: shotName, elapsed_ms: Date.now() - t0 });
      emit({ type: 'step_end', ...results[results.length - 1] });
      if (status === 'failed') {
        failed++;
        emit({ type: 'done', status: 'failed',
               summary: { total: job.steps.length, passed: results.length - failed,
                          failed, duration_ms: Date.now() - t0 },
               report_path: rt.reportFile() });
        return { status: 'failed' };
      }
    }
    emit({ type: 'done', status: 'completed',
           summary: { total: job.steps.length, passed: results.length, failed: 0,
                      duration_ms: Date.now() - t0 },
           report_path: rt.reportFile() });
    return { status: 'completed' };
  } finally {
    await rt.close?.();
  }
}

const entry = process.argv[2];
// 直跑判定:vitest 等导入方不会把 main.js 放在 process.argv[1],据此区分;entry 为 job.json 路径
import { pathToFileURL } from 'node:url';
const isMain = Boolean(process.argv[1]) && import.meta.url === pathToFileURL(process.argv[1]).href;
// 入口辅助:readJob 同步抛错与 runJob 异步失败统一收敛为 error 事件,返回进程退出码(0/1)。
// agents.js 仍在函数体内动态导入,vitest 等导入方不会触发 Midscene 加载。
export async function runEntry(entry, emit) {
  try {
    const job = readJob(entry);
    await runJob(job, { createRuntime: (await import('./agents.js')).createRuntime, emit });
    return 0;
  } catch (e) {
    emit({ type: 'error', message: String(e?.message || e).slice(0, 500) });
    return 1;
  }
}
if (isMain && entry) {
  runEntry(entry, createEmitter()).then((code) => { process.exitCode = code; });
}
