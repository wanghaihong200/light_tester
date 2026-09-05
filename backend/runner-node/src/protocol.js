// runner-node/src/protocol.js
// stdout NDJSON 协议:一行一个 JSON 事件(schema 与平台 SSE 执行事件一致,见计划 10「Node 执行协议」)。
import { readFileSync } from 'node:fs';

export function createEmitter(write = (s) => process.stdout.write(s)) {
  return (event) => write(JSON.stringify(event) + '\n');
}

export function readJob(path) {
  const job = JSON.parse(readFileSync(path, 'utf-8'));
  if (!Array.isArray(job.steps)) throw new Error('job.steps 必须是数组');
  job.variables = job.variables || {};
  return job;
}
