# 状态面板（小程序端）

微信小程序端，原生 TypeScript 实现，无 npm 运行时依赖。

## 开发

微信开发者工具导入本目录（AppID 已配置），本地后端地址在 `config.ts` 的 `BASE_URL` 配置，开发期需在「详情 → 本地设置」勾选「不校验合法域名」。

类型检查：

```bash
npx tsc --noEmit
```

## 目录结构

```
miniprogram/
├── app.ts            # 入口：版本更新、全局错误上报
├── app.json          # 全局配置（页面注册、窗口、DarkMode）
├── app.wxss          # 全局样式（设计 Token）
├── theme.json        # DarkMode 主题变量
├── config.ts         # 服务端地址等常量
├── pages/index/      # 页面
├── utils/            # request（网络请求）、logger（实时日志）
└── typings/          # 微信官方类型定义（本地化）
```
