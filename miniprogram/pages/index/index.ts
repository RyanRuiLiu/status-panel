import { http } from '../../utils/request'
import { fetchLaundryStatus } from '../../utils/laundry'
import { fetchShowerStatus } from '../../utils/shower'
import { fetchDisplayConfig, cachedConfig, type DisplayConfig } from '../../utils/remote-config'
import { formatUpdatedAt } from '../../utils/relative-time'

interface ElectricityStatus {
  balance: number | null
  sampled_at: string | null
  today_usage: number | null
  yesterday_usage: number | null
  week_usage: number | null
  month_usage: number | null
  estimated_days: number | null
}

interface StatItem {
  label: string
  value: string
}

/** 卡片展示模型：数字与时间在进入视图前格式化完毕。 */
interface ElectricityCard {
  balance: string
  estimated: string
  stats: StatItem[]
  updated: string
}

interface LaundryCard {
  machines: Array<{ name: string; state: string; tone: string }>
  updatedAt: string
}

interface ShowerCard {
  doors: Array<{ no: string; state: string; key: string }>
  updatedAt: string
}

/** 卡片数据态：loading（首进加载中）/ ready（有数据）/ empty（确认无数据）/ failed（本次失败且无旧数据）。 */
type CardState = 'loading' | 'ready' | 'empty' | 'failed'

/** 用量：1 位小数；无法计算显示 —。 */
function formatUsage(v: number | null): string {
  return v === null ? '—' : `${v.toFixed(1)} 度`
}

Page({
  data: {
    card: null as ElectricityCard | null,
    laundry: null as LaundryCard | null,
    shower: null as ShowerCard | null,
    electricityState: 'loading' as CardState,
    laundryState: 'loading' as CardState,
    showerState: 'loading' as CardState,
  },

  onShow() {
    this.refresh()
  },

  onPullDownRefresh() {
    this.refresh(true).finally(() => wx.stopPullDownRefresh())
  },

  /** 三个数据源独立刷新（我们后端 / 厂商 / ntu-shower 互不影响）。下拉失败给 toast，进入时静默。 */
  async refresh(viaPullDown = false) {
    // 配置先行（失败回落缓存）；配置不可得时配置驱动卡片维持失败/空态
    const config: DisplayConfig | null = (await fetchDisplayConfig()) ?? cachedConfig()
    // 禁用数组解构：开发者工具 SWC 编译对该写法引入 @swc/runtime 助手模块，零依赖架构无 npm 产物会运行时崩溃
    const results = await Promise.all([
      this.refreshElectricity(),
      config ? this.refreshLaundry(config) : Promise.resolve(false),
      config ? this.refreshShower(config) : Promise.resolve(false),
    ])
    const electricityOk = results[0] === true
    const laundryOk = results[1] === true
    const showerOk = results[2] === true
    if (viaPullDown && !(electricityOk && laundryOk && showerOk)) {
      wx.showToast({ title: '刷新失败', icon: 'none' })
    }
  },

  async refreshElectricity(): Promise<boolean> {
    try {
      const s = await http.get<ElectricityStatus>('/api/v1/electricity')
      const card: ElectricityCard | null =
        s.balance === null
          ? null // 从未采样：空态
          : {
              balance: s.balance.toFixed(2),
              estimated:
                s.estimated_days === null ? '预计可用 —' : `预计可用 ${s.estimated_days} 天`,
              stats: [
                { label: '今日', value: formatUsage(s.today_usage) },
                { label: '昨日', value: formatUsage(s.yesterday_usage) },
                { label: '近7天', value: formatUsage(s.week_usage) },
                { label: '近30天', value: formatUsage(s.month_usage) },
              ],
              updated:
                s.sampled_at === null
                  ? '暂无采样数据'
                  : `更新于 ${formatUpdatedAt(new Date(s.sampled_at))}`,
            }
      this.setData({ card, electricityState: card ? 'ready' : 'empty' })
      return true
    } catch {
      // 失败：有旧数据保留展示（更新于如实变旧）；无旧数据标 failed
      if (!this.data.card) this.setData({ electricityState: 'failed' })
      return false
    }
  },

  async refreshLaundry(config: DisplayConfig): Promise<boolean> {
    const machines = await fetchLaundryStatus(config.laundry.machines) // 单台失败已在内部归一
    // 厂商响应无数据时刻字段：更新于 = 三台查询齐全的时刻（驻留期档位自然增长）
    this.setData({ laundry: { machines, updatedAt: formatUpdatedAt(new Date()) } })
    this.setData({ laundryState: 'ready' })
    return machines.every((m) => m.state !== '查询失败')
  },

  async refreshShower(config: DisplayConfig): Promise<boolean> {
    const status = await fetchShowerStatus(config.shower)
    if (status === null) {
      // 失败：有旧数据保留展示；无旧数据标 failed
      if (!this.data.shower) this.setData({ showerState: 'failed' })
      return false
    }
    if (status.doors.length === 0) {
      this.setData({ showerState: 'empty' })
      return false
    }
    this.setData({
      // 更新于 = 快照时刻（reported_at 最大值），如实反映数据新旧而非查询时刻
      shower: {
        doors: status.doors,
        updatedAt:
          status.reportedAt === null ? '暂无数据' : formatUpdatedAt(new Date(status.reportedAt)),
      },
      showerState: 'ready',
    })
    return true
  },
})
