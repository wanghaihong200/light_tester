import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { runEntry, runJob } from '../src/main.js';

function fakeRuntime(script) {
  let n = 0;
  return {
    agent: {}, page: null,
    async launch() {},
    async screenshot() { return Buffer.from(`shot${n++}`); },
    reportFile() { return 'report/x.html'; },
    async close() { this.closed = true; },
    // 第 step 序号为 1 的 ai_assert 抛错(模拟 grounding 失败)
    __script: script,
  };
}

function factory(agentFailAt) {
  return async (job) => {
    const rt = fakeRuntime(job);
    rt.agent = {
      async aiAssert(a) { if (a.includes('炸') ) throw new Error('boom'); },
      async aiTap() {},
    };
    return rt;
  };
}

const eventsOf = (emitted) => emitted.map((e) => e.type);

describe('runJob 主循环', () => {
  it('全过:逐步事件+done completed+报告路径', async () => {
    const emitted = [];
    const outDir = mkdtempSync(join(tmpdir(), 'run-'));
    const job = { run_id: 1, target: 'web', out_dir: outDir, variables: {},
                  steps: [{ id: 'a', action: 'ai_tap', params: { target: '按钮' } },
                          { id: 'b', action: 'ai_tap', params: { target: '按钮2' } }] };
    const r = await runJob(job, { createRuntime: factory(), emit: (e) => emitted.push(e) });
    expect(r.status).toBe('completed');
    expect(eventsOf(emitted)).toEqual(['step_start', 'step_start', 'frame', 'step_end', 'step_start', 'frame', 'step_end', 'done']);
    const done = emitted.at(-1);
    expect(done.summary).toEqual({ total: 2, passed: 2, failed: 0, duration_ms: expect.any(Number) });
    expect(done.report_path).toBe('report/x.html');
  });

  it('fail-fast:第二步失败即 done failed,第三步不执行', async () => {
    const emitted = [];
    const outDir = mkdtempSync(join(tmpdir(), 'run-'));
    const job = { run_id: 2, target: 'web', out_dir: outDir, variables: {},
                  steps: [{ id: 'a', action: 'ai_assert', params: { assertion: 'ok' } },
                          { id: 'b', action: 'ai_assert', params: { assertion: '炸' } },
                          { id: 'c', action: 'ai_assert', params: { assertion: 'ok' } }] };
    const r = await runJob(job, { createRuntime: factory(), emit: (e) => emitted.push(e) });
    expect(r.status).toBe('failed');
    const stepEnds = emitted.filter((e) => e.type === 'step_end');
    expect(stepEnds).toHaveLength(2);
    expect(stepEnds[1].status).toBe('failed');
    expect(stepEnds[1].error).toContain('boom');
    const done = emitted.at(-1);
    expect(done.status).toBe('failed');
    expect(done.summary).toMatchObject({ total: 3, passed: 1, failed: 1 });
  });
});

describe('runEntry 入口(直跑形态)', () => {
  it('readJob 同步抛错(路径不存在)也转 error 事件并返回失败退出码', async () => {
    const emitted = [];
    const code = await runEntry(join(tmpdir(), `nope-${Date.now()}.json`), (e) => emitted.push(e));
    expect(code).toBe(1);
    expect(emitted).toHaveLength(1);
    expect(emitted[0].type).toBe('error');
    expect(emitted[0].message).toContain('ENOENT');
  });
});
