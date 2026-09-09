import { beforeEach, describe, expect, it, vi } from 'vitest'

// vi.mock 工厂被提升到文件顶,httpMock 须随 hoisted 提升才能在工厂内引用(同 mock-api.spec 风格)
const httpMock = vi.hoisted(() => ({
  get: vi.fn(async () => ({})),
  post: vi.fn(async () => ({})),
  del: vi.fn(async () => ({})),
}))
vi.mock('../../src/api/client', () => ({ http: httpMock }))

import {
  comparePerfRecords, deletePerfRecord, getPerfRecord, getPerfRecordSeries, getPerfTrend,
  importPerfHistory, listDevicePerfHistory, listPerfRecords,
} from '../../src/api/perf'

describe('perf api 路径与载荷', () => {
  beforeEach(() => {
    httpMock.get.mockClear()
    httpMock.post.mockClear()
    httpMock.del.mockClear()
  })

  it('listPerfRecords 不带过滤 → 无查询串', async () => {
    await listPerfRecords(7)
    expect(httpMock.get).toHaveBeenCalledWith('/projects/7/perf-records')
  })

  it('listPerfRecords 三过滤全带 → 按序拼查询串', async () => {
    await listPerfRecords(7, { source: 'import', script_id: 3, device_serial: 'DEV-A' })
    expect(httpMock.get).toHaveBeenCalledWith('/projects/7/perf-records?source=import&script_id=3&device_serial=DEV-A')
  })

  it('listPerfRecords 部分过滤 → 空参数不拼;URLSearchParams 转义一次不双编', async () => {
    await listPerfRecords(7, { device_serial: 'a&b' })
    expect(httpMock.get).toHaveBeenCalledWith('/projects/7/perf-records?device_serial=a%26b')
    await listPerfRecords(7, {})
    expect(httpMock.get).toHaveBeenLastCalledWith('/projects/7/perf-records')
  })

  it('getPerfRecord / getPerfRecordSeries / deletePerfRecord 单资源端点', async () => {
    await getPerfRecord(9)
    expect(httpMock.get).toHaveBeenCalledWith('/perf-records/9')
    await getPerfRecordSeries(9)
    expect(httpMock.get).toHaveBeenCalledWith('/perf-records/9/series')
    await deletePerfRecord(9)
    expect(httpMock.del).toHaveBeenCalledWith('/perf-records/9')
  })

  it('comparePerfRecords POST record_ids', async () => {
    await comparePerfRecords(7, [2, 3])
    expect(httpMock.post).toHaveBeenCalledWith('/projects/7/perf-records/compare', { record_ids: [2, 3] })
  })

  it('getPerfTrend 不带过滤 → 无查询串;带过滤 → script_id + device_serial', async () => {
    await getPerfTrend(7)
    expect(httpMock.get).toHaveBeenCalledWith('/projects/7/perf-trend')
    await getPerfTrend(7, { script_id: 3, device_serial: 'DEV-A' })
    expect(httpMock.get).toHaveBeenCalledWith('/projects/7/perf-trend?script_id=3&device_serial=DEV-A')
  })

  it('listDevicePerfHistory 默认 limit=50;可覆盖;serial 转义', async () => {
    await listDevicePerfHistory('DEV-A')
    expect(httpMock.get).toHaveBeenCalledWith(`/app-devices/DEV-A/perf-history?limit=50`)
    await listDevicePerfHistory('DEV-A', 10)
    expect(httpMock.get).toHaveBeenCalledWith(`/app-devices/DEV-A/perf-history?limit=10`)
    await listDevicePerfHistory('a/b')
    expect(httpMock.get).toHaveBeenCalledWith(`/app-devices/${encodeURIComponent('a/b')}/perf-history?limit=50`)
  })

  it('importPerfHistory POST serial/history_id;name 缺省不带键', async () => {
    await importPerfHistory(7, { serial: 'DEV-A', history_id: 'performance-abc', name: '导入A' })
    expect(httpMock.post).toHaveBeenCalledWith('/projects/7/perf-records/import',
      { serial: 'DEV-A', history_id: 'performance-abc', name: '导入A' })
    await importPerfHistory(7, { serial: 'DEV-A', history_id: 'performance-abc' })
    expect(httpMock.post).toHaveBeenLastCalledWith('/projects/7/perf-records/import',
      { serial: 'DEV-A', history_id: 'performance-abc' })
  })
})
