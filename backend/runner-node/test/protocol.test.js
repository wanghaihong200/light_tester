import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { createEmitter, readJob } from '../src/protocol.js';

describe('protocol', () => {
  it('emit 每事件一行合法 JSON', () => {
    const lines = [];
    const emit = createEmitter((s) => lines.push(s));
    emit({ type: 'step_start', index: 0 });
    emit({ type: 'done', status: 'completed', summary: {} });
    expect(lines).toHaveLength(2);
    expect(JSON.parse(lines[0])).toEqual({ type: 'step_start', index: 0 });
    expect(lines[1].endsWith('\n')).toBe(true);
  });

  it('readJob 校验 steps 并补默认 variables', () => {
    const dir = mkdtempSync(join(tmpdir(), 'job-'));
    const p = join(dir, 'job.json');
    writeFileSync(p, JSON.stringify({ run_id: 1, steps: [] }));
    const job = readJob(p);
    expect(job.variables).toEqual({});
    writeFileSync(p, JSON.stringify({ run_id: 1 }));
    expect(() => readJob(p)).toThrow(/steps/);
  });
});
