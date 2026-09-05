import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listDocuments: vi.fn().mockResolvedValue([
    { id: 7, filename: '需求文档.md', uploaded_at: '2026-08-15T09:00:00' },
  ]),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
}))
vi.mock('../../src/api/documents', () => api)

import DocumentsPane from '../../src/components/DocumentsPane.vue'

describe('DocumentsPane', () => {
  it('加载并渲染文档列表', async () => {
    const wrapper = mount(DocumentsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(api.listDocuments).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('需求文档.md')
  })

  it('upload 的 accept 限制为 .md', async () => {
    const wrapper = mount(DocumentsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.find('input[type="file"]').attributes('accept')).toBe('.md')
  })
})
