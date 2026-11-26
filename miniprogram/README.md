# 状态面板（小程序端）

## 概述

本目录为微信小程序的客户端实现，采用原生 TypeScript。运行时不依赖 npm 包，开发依赖仅包含 TypeScript。

## 开发环境

1. 使用微信开发者工具导入 `miniprogram/` 目录；`project.config.json` 已配置 `appid`。
2. `config.ts` 中的 `BASE_URL` 为生产服务地址 `https://status-panel.ryanliu.cn`。本地开发时应替换为 `http://127.0.0.1:8000`，该本地值不得提交。
3. 本地连接开发服务时，应在微信开发者工具的「详情 → 本地设置」中关闭域名校验。

## 类型检查

```bash
npm ci
npx tsc --noEmit
```

上述命令与 `.github/workflows/ci.yml` 中 `miniprogram` job 保持一致。

## 目录结构

```
miniprogram/
├── app.ts            # 应用入口：版本更新与全局错误上报
├── app.json          # 全局配置：页面注册、窗口与 DarkMode
├── app.wxss          # 全局样式与设计 Token
├── theme.json        # DarkMode 主题变量
├── config.ts         # 服务端地址等常量
├── package.json      # TypeScript 开发依赖
├── tsconfig.json     # TypeScript 编译配置
├── pages/index/      # 页面实现
├── utils/            # 网络请求、日志、洗衣机、浴室、相对时间与远程配置工具
└── typings/          # 微信官方类型定义
```
