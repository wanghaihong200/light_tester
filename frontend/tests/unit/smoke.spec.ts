import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import App from '../../src/App.vue'

describe('App shell', () => {
  it('渲染 router-view 壳', () => {
    const wrapper = mount(App, { global: { stubs: { 'router-view': true } } })
    expect(wrapper.exists()).toBe(true)
  })
})
