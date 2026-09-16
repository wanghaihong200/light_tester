import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getJenkinsConnection: vi.fn(),
  putJenkinsConnection: vi.fn(),
  testJenkinsConnection: vi.fn(),
}))
vi.mock('../../src/api/cicd', () => api)

import JenkinsConfigCard from '../../src/components/cicd/JenkinsConfigCard.vue'

describe('JenkinsConfigCard', () => {
  it('加载已存配置并保存', async () => {
    api.getJenkinsConnection.mockResolvedValue({
      configured: true, base_url: 'http://localhost:8081', api_user: 'admin', api_token: 'tok',
      gitlab_exposed_base: 'http://host.docker.internal:8090', credential_id: 'gitlab-creds',
    })
    api.putJenkinsConnection.mockResolvedValue({})
    const w = mount(JenkinsConfigCard, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect((w.vm as unknown as { form: { base_url: string } }).form.base_url).toBe('http://localhost:8081')
    ;(w.vm as unknown as { save: () => Promise<void> }).save()
    await flushPromises()
    expect(api.putJenkinsConnection).toHaveBeenCalled()
  })

  it('测试连接成功/失败提示', async () => {
    api.getJenkinsConnection.mockResolvedValue({ configured: false, base_url: '', api_user: '', api_token: '', gitlab_exposed_base: 'http://host.docker.internal:8090', credential_id: 'gitlab-creds' })
    api.testJenkinsConnection.mockResolvedValueOnce({ ok: true }).mockRejectedValueOnce(new Error('Jenkins 不可达'))
    const w = mount(JenkinsConfigCard, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    ;(w.vm as unknown as { doTest: () => Promise<void> }).doTest()
    await flushPromises()
    expect(w.text()).toContain('连接成功')
    ;(w.vm as unknown as { doTest: () => Promise<void> }).doTest()
    await flushPromises()
    expect(w.text()).toContain('Jenkins 不可达')
  })
})
