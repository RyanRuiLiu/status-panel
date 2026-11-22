/** 实时日志封装（官方建议形态：独立模块统一出入口）。

- 从 We分析「性能质量 → 实时日志」按页面/微信号检索；
- 日志按页面聚合并实时上报；开发者工具调用不实际上报，仅真机生效；
- 限制：单条 5KB / 200 次调用，避免循环内打日志；
- 基础库 2.7.1+，最低基础库由小程序后台配置保障。
*/

const rtlog = wx.getRealtimeLogManager()

export const logger = {
  warn(...args: unknown[]) {
    rtlog.warn(...args)
  },
  error(...args: unknown[]) {
    rtlog.error(...args)
  },
}
