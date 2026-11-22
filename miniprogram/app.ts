/** 入口：注册版本更新提示与全局错误上报。

官方机制：
- 版本更新：wx.getUpdateManager（基础库 1.9.90+）→ 客户端自动下载新版本 →
  onUpdateReady 回调 → 弹窗确认 → applyUpdate 强制重启；
  开发者工具用「编译模式 → 下次编译模拟更新」调试（开发版/体验版无版本概念，无法真测）。
- 全局错误：官方推荐以 wx.onError / wx.onUnhandledRejection 绑定（而非 App 参数），
  未捕获错误统一进实时日志，是线上问题定位的唯一通道。
*/

import { logger } from './utils/logger'

App({
  onLaunch() {
    const updateManager = wx.getUpdateManager()
    updateManager.onUpdateReady(() => {
      wx.showModal({
        title: '更新提示',
        content: '新版本已经准备好，是否重启应用？',
        success: (res) => {
          if (res.confirm) updateManager.applyUpdate()
        },
      })
    })
  },
})

wx.onError((error) => logger.error('app.onError', String(error)))

wx.onUnhandledRejection((res) => logger.error('unhandledRejection', String(res.reason)))
