import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { collectAndroidSnapshot, listCrossScripts, listRunsByTarget } from '../../src/api/crossAutomation';

describe('crossAutomation api', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('listCrossScripts 走 scope=cross', async () => {
    await listCrossScripts(7);
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain('/projects/7/ui-scripts?scope=cross');
  });

  it('listRunsByTarget 带端筛选', async () => {
    await listRunsByTarget(7, 'android');
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain('/projects/7/ui-runs?driver_target=android');
    await listRunsByTarget(7);
    expect(vi.mocked(fetch).mock.calls[1][0]).not.toContain('driver_target');
  });

  it('collectAndroidSnapshot POST 端点与包名', async () => {
    await collectAndroidSnapshot(7, { name: '快照A', app_package: 'com.demo.app' });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain('/ui-auth-states/android-snapshot');
    expect((init as RequestInit).method).toBe('POST');
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ name: '快照A', app_package: 'com.demo.app' });
  });
});
