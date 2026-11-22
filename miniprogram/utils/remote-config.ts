/** 展示配置拉取与本地缓存（值的变化不依赖发版）。

- 配置由后端 GET /api/v1/config 下发，按域分组（laundry / shower）；
- 成功后写本地缓存；拉取失败时调用方回落缓存——后端短暂不可用不影响已安装用户。
*/

import { BASE_URL, REQUEST_TIMEOUT_MS } from '../config'
import { logger } from './logger'

export interface LaundryMachineConfig {
  goods_id: string
  label: string
}

export interface DisplayConfig {
  laundry: { machines: LaundryMachineConfig[] }
  shower: { base_url: string; device_id: string }
}

const STORAGE_KEY = 'display_config'

/** 信任边界：后端响应（与缓存值）必须符合契约才可用，否则视为本次拉取失败。 */
function isDisplayConfig(v: unknown): v is DisplayConfig {
  if (typeof v !== 'object' || v === null) return false
  const c = v as DisplayConfig
  return (
    Array.isArray(c.laundry?.machines) &&
    c.laundry.machines.every(
      (m) => m !== null && typeof m === 'object' && typeof m.goods_id === 'string' && typeof m.label === 'string',
    ) &&
    typeof c.shower?.base_url === 'string' &&
    typeof c.shower?.device_id === 'string'
  )
}

/** 上次成功拉取的配置；从未成功过或缓存损坏返回 null。 */
export function cachedConfig(): DisplayConfig | null {
  const raw: unknown = wx.getStorageSync(STORAGE_KEY)
  if (!isDisplayConfig(raw)) {
    wx.removeStorageSync(STORAGE_KEY) // 缓存损坏：清掉，避免永远命中坏值
    return null
  }
  return raw
}

/** 拉取最新配置并更新缓存；失败或契约不符返回 null（缓存保持不动）。 */
export function fetchDisplayConfig(): Promise<DisplayConfig | null> {
  return new Promise((resolve) => {
    wx.request({
      url: `${BASE_URL}/api/v1/config`,
      method: 'GET',
      timeout: REQUEST_TIMEOUT_MS,
      success: (res) => {
        if (res.statusCode >= 400) {
          logger.warn('config', res.statusCode)
          resolve(null)
          return
        }
        const cfg: unknown = res.data
        if (!isDisplayConfig(cfg)) {
          logger.warn('config', '契约不符')
          resolve(null)
          return
        }
        wx.setStorageSync(STORAGE_KEY, cfg)
        resolve(cfg)
      },
      fail: () => {
        logger.warn('config', 'fetch failed')
        resolve(null)
      },
    })
  })
}
