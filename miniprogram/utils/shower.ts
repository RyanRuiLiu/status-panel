/** 浴室喷头状态（直连 ntu-shower 服务端，纯展示）。

接口契约（ntu-shower 公开只读端点，架构文档定为用户面无凭据查询）：
- GET {base_url}/api/v1/doors?device_id=… → 喷头现态数组（每行含 reported_at 采集时刻）。

数据新鲜度：不用设备在线状态另发请求，直接取各行 reported_at 最大值——
它如实反映快照新旧，设备离线时自然停走，单请求即诚实。
状态中文名是 ntu-shower 的单一数据源（doors/schemas 的 _STATE_LABELS），照抄映射；
未知新状态原样透传原文。隐私边界：不读取 last_used_cert 等人相关字段。
*/

import { REQUEST_TIMEOUT_MS } from '../config'
import { logger } from './logger'

const STATE_LABEL: Record<string, string> = {
  free: '空闲',
  selected: '已选中',
  waiting: '等待开阀',
  bathing: '淋浴中',
  paused: '已暂停',
  repair: '维修中',
  disabled: '已禁用',
}

const KNOWN_STATES = new Set(Object.keys(STATE_LABEL))

export interface DoorView {
  no: string
  state: string
  /** 状态原值（free/selected/…，未知为 unknown），作样式类名供逐态着色。 */
  key: string
}

export interface ShowerStatus {
  /** 全部喷头 reported_at 的最大值（ISO），即快照时刻。 */
  reportedAt: string | null
  doors: DoorView[]
}

interface DoorEnvelope {
  device_id: string
  door_no: number
  state: string
  reported_at: string
}

/** 信任边界：ntu-shower 200 响应必须是行数组且各行字段齐全，否则视为本次查询失败。 */
function isDoorRows(v: unknown): v is DoorEnvelope[] {
  return (
    Array.isArray(v) &&
    v.every(
      (r) =>
        r !== null &&
        typeof r === 'object' &&
        typeof r.device_id === 'string' &&
        typeof r.door_no === 'number' &&
        typeof r.state === 'string' &&
        typeof r.reported_at === 'string',
    )
  )
}

function getJSON<T>(url: string): Promise<T> {
  return new Promise((resolve, reject) => {
    wx.request({
      url,
      method: 'GET',
      timeout: REQUEST_TIMEOUT_MS,
      success: (res) => {
        if (res.statusCode >= 400) {
          reject(new Error(`HTTP ${res.statusCode}`))
          return
        }
        resolve(res.data as T)
      },
      fail: (err) => reject(new Error(err.errMsg ?? '网络异常')),
    })
  })
}

/** 查询目标设备的喷头现态（单请求）。 */
export async function fetchShowerStatus(cfg: {
  base_url: string
  device_id: string
}): Promise<ShowerStatus | null> {
  const base = cfg.base_url.replace(/\/+$/, '')
  let rows: unknown
  try {
    rows = await getJSON<unknown>(`${base}/api/v1/doors?device_id=${cfg.device_id}`)
  } catch (e) {
    logger.warn('shower', e instanceof Error ? e.message : 'doors failed')
    return null
  }
  if (!isDoorRows(rows)) {
    logger.warn('shower', '契约不符')
    return null
  }

  const mine = rows.filter((d) => d.device_id === cfg.device_id)
  const sortedTimes = mine.map((d) => d.reported_at).sort()
  const reportedAt = sortedTimes.length ? sortedTimes[sortedTimes.length - 1] : null
  const doors: DoorView[] = mine
    .sort((a, b) => a.door_no - b.door_no)
    .map((d) => ({
      no: `${d.door_no}号`,
      state: STATE_LABEL[d.state] ?? d.state, // 未知新状态透传原文
      key: KNOWN_STATES.has(d.state) ? d.state : 'unknown',
    }))
  return { reportedAt, doors }
}
