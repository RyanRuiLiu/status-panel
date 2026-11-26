/** 洗衣机状态查询（直连厂商「胖乖生活」userapi.qiekj.com）。

接口契约（厂商无公开文档，以下为实测确认的事实）：
- POST /goods/normal/details，application/x-www-form-urlencoded，body 仅 goodsId；
- 无需登录凭据与签名头，仅需常规浏览器 UA（网关 WAF 拦截非常规 UA）；
- 响应信封 {code, msg, data, t}，code==0 成功。

状态语义：soldState 1=可售 2=不可售（实测洗衣机使用中置 2）；
deviceErrorCode null/0=正常 2=工作中 4=故障 7=被预约 8/12/4204=离线
4000=未绑定 4107=故障 4111=停用 10/13=IOT 错误。

展示机器清单由后端配置下发（remote-config），本模块不持有清单。
*/

import { REQUEST_TIMEOUT_MS } from '../config'
import { logger } from './logger'
import type { LaundryMachineConfig } from './remote-config'

export type LaundryMachine = LaundryMachineConfig

const DETAILS_URL = 'https://userapi.qiekj.com/goods/normal/details'

/** 已知错误码 → 状态词（厂商 App 官方字面量的短语形态）。 */
const ERROR_STATE: Record<string, { text: string; tone: 'danger' | 'muted' }> = {
  '2': { text: '使用中', tone: 'danger' },
  '4': { text: '故障', tone: 'danger' },
  '7': { text: '已预约', tone: 'muted' },
  '8': { text: '离线', tone: 'muted' },
  '10': { text: '故障', tone: 'danger' },
  '12': { text: '离线', tone: 'muted' },
  '13': { text: '故障', tone: 'danger' },
  '4000': { text: '未绑定', tone: 'muted' },
  '4107': { text: '故障', tone: 'danger' },
  '4111': { text: '已停用', tone: 'muted' },
  '4204': { text: '离线', tone: 'muted' },
}

export interface MachineView {
  name: string
  state: string
  tone: 'success' | 'danger' | 'muted'
}

interface DetailsEnvelope {
  code: number
  data: { soldState?: number; deviceErrorCode?: number | string; deviceErrorMsg?: string } | null
}

/** 信任边界：厂商 200 响应可能非 JSON（实测 405 时返回过 HTML）或缺字段，先验形状再消费。 */
function isDetailsEnvelope(v: unknown): v is DetailsEnvelope {
  if (typeof v !== 'object' || v === null) return false
  const e = v as DetailsEnvelope
  if (typeof e.code !== 'number') return false
  return e.data === null || (typeof e.data === 'object' && typeof e.data.soldState === 'number')
}

function toView(machine: LaundryMachine, data: DetailsEnvelope['data']): MachineView {
  const name = machine.label
  if (data === null) {
    return { name, state: '异常', tone: 'muted' }
  }
  const err = data.deviceErrorCode == null ? '' : String(data.deviceErrorCode)
  if (err === '' || err === '0') {
    if (data.soldState === 2) {
      return { name, state: '使用中', tone: 'danger' }
    }
    return { name, state: '空闲', tone: 'success' }
  }
  const known = ERROR_STATE[err]
  if (known) {
    return { name, state: known.text, tone: known.tone }
  }
  // 未知错误码：显示厂商自带错误文案（官方原文），无则异常
  return { name, state: data.deviceErrorMsg || '异常', tone: 'muted' }
}

function fetchOne(machine: LaundryMachine): Promise<MachineView> {
  const failed: MachineView = { name: machine.label, state: '查询失败', tone: 'muted' }
  return new Promise((resolve) => {
    wx.request({
      url: DETAILS_URL,
      method: 'POST',
        data: { goodsId: machine.goods_id },
      timeout: REQUEST_TIMEOUT_MS,
      header: { 'content-type': 'application/x-www-form-urlencoded' },
      success: (res) => {
        if (res.statusCode >= 400) {
          resolve(failed)
          return
        }
        const body: unknown = res.data
        if (!isDetailsEnvelope(body)) {
          // 200 但契约不符（厂商改版/网关劫持页）：显式异常态，不猜字段
          resolve({ name: machine.label, state: '异常', tone: 'muted' })
          return
        }
        resolve(toView(machine, body.code === 0 ? body.data : null))
      },
      fail: () => {
        logger.error('laundry', machine.goods_id, '查询失败')
        resolve(failed)
      },
    })
  })
}

/** 并行查询全部展示机器（单台失败不影响其他台）。 */
export function fetchLaundryStatus(machines: LaundryMachine[]): Promise<MachineView[]> {
  return Promise.all(machines.map(fetchOne))
}
