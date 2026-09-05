import { describe, expect, it } from 'vitest'
import { stagedToMindmap, stagedTotal } from '../../src/adapters/staging'
import type { StagingGroup } from '../../src/types'

describe('stagedToMindmap', () => {
  const groups: StagingGroup[] = [
    {
      feature_point_name: '账号登录',
      cases: [
        {
          id: 1,
          job_id: 10,
          feature_point_name: '账号登录',
          title: '登录成功',
          priority: 'P0',
          precondition: null,
          remark: null,
          steps: [{ action: '输入账号', expected: '显示登录框' }],
          created_at: '2026-08-16T00:00:00',
        },
        {
          id: 2,
          job_id: 10,
          feature_point_name: '账号登录',
          title: '密码错误',
          priority: 'P1',
          precondition: null,
          remark: null,
          steps: [{ action: '输入错误密码', expected: '提示错误' }],
          created_at: '2026-08-16T00:00:00',
        },
      ],
    },
    {
      feature_point_name: '扫码登录',
      cases: [
        {
          id: 3,
          job_id: 10,
          feature_point_name: '扫码登录',
          title: '二维码过期',
          priority: 'P2',
          precondition: null,
          remark: null,
          steps: [{ action: '等待过期', expected: '提示过期' }],
          created_at: '2026-08-16T00:00:00',
        },
      ],
    },
  ]

  it('根节点为模块名,nodeType=root', () => {
    const mm = stagedToMindmap('登录模块', groups)
    expect(mm.data.text).toBe('登录模块')
    expect(mm.data.nodeType).toBe('root')
    expect(mm.data.uid).toBe('root')
  })

  it('第一个功能点节点正确', () => {
    const mm = stagedToMindmap('登录模块', groups)
    expect(mm.children[0].data.nodeType).toBe('feature')
    expect(mm.children[0].data.text).toBe('账号登录')
    expect(mm.children[0].data.uid).toBe('staged-fp-0')
    expect(mm.children[0].data).not.toHaveProperty('refId')
  })

  it('第一个功能点下第一条用例正确', () => {
    const mm = stagedToMindmap('登录模块', groups)
    const firstCase = mm.children[0].children[0]
    expect(firstCase.data.text).toBe('[P0] 登录成功')
    expect(firstCase.data.nodeType).toBe('case')
    expect(firstCase.data.uid).toBe('staged-case-1')
    expect(firstCase.data).not.toHaveProperty('refId')
    expect(firstCase.children).toEqual([])
  })

  it('组保持传入顺序,组内保持用例顺序', () => {
    const mm = stagedToMindmap('登录模块', groups)
    expect(mm.children[0].data.text).toBe('账号登录')
    expect(mm.children[1].data.text).toBe('扫码登录')
    expect(mm.children[0].children[0].data.text).toBe('[P0] 登录成功')
    expect(mm.children[0].children[1].data.text).toBe('[P1] 密码错误')
    expect(mm.children[1].children[0].data.text).toBe('[P2] 二维码过期')
  })

  it('空数组返回只有根节点的树', () => {
    const mm = stagedToMindmap('空模块', [])
    expect(mm.data.text).toBe('空模块')
    expect(mm.data.nodeType).toBe('root')
    expect(mm.data.uid).toBe('root')
    expect(mm.children.length).toBe(0)
  })
})

describe('stagedTotal', () => {
  it('计算总用例数', () => {
    const groups: StagingGroup[] = [
      {
        feature_point_name: 'A',
        cases: [
          { id: 1, job_id: 10, feature_point_name: 'A', title: 'a1', priority: 'P0', precondition: null, remark: null, steps: [], created_at: '2026-08-16' },
          { id: 2, job_id: 10, feature_point_name: 'A', title: 'a2', priority: 'P1', precondition: null, remark: null, steps: [], created_at: '2026-08-16' },
        ],
      },
      {
        feature_point_name: 'B',
        cases: [
          { id: 3, job_id: 10, feature_point_name: 'B', title: 'b1', priority: 'P2', precondition: null, remark: null, steps: [], created_at: '2026-08-16' },
        ],
      },
    ]
    expect(stagedTotal(groups)).toBe(3)
  })

  it('空数组返回 0', () => {
    expect(stagedTotal([])).toBe(0)
  })
})
