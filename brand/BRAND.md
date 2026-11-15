# Vela 品牌视觉

本阶段将确定的 Vela 航海科技 Logo 作为正式视觉方向：**V 字母 + 扬帆 + 服务器状态条**。

- `vela-logo-horizontal.png`：横版 Logo，透明背景。可用于 README、网站或 Bot 介绍。
- `vela-app-512.png`：深海蓝圆角方形 APP 主图标。`vela-app-16/24/32/48/64/128/192/256.png` 是缩放版本。
- `frontend/src/assets/vela-mark.png`：由 Vite 引用的图标，构建后进入带内容哈希的资源文件。
- `frontend/public/icons/vela-*.png`：供 PWA Manifest/图标路由使用；保留原版 3x-ui 图标文件供兼容。

品牌名称只影响展示和发行资产。原 Fork URL、Go module path、API 路由与节点同步协议保持兼容。

## 注意

图标已做透明底和方形缩略版，但生产发布前仍建议在 Android、iOS、Telegram 不同主题下检查 16px、32px、192px 的可读性。Logo 是目前确认的视觉方向；本包不包含可编辑矢量源文件。
