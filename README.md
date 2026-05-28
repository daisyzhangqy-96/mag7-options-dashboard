# MAG7 期权策略雷达

基于富途 OpenAPI 的 MAG7 盘前期权策略列表。

---

## 本地使用

前提：富途 OpenD 已在 `127.0.0.1:11111` 运行。

双击 `run.bat`：自动生成数据→起本地服务→后台每 10 分钟刷新。

---

## 云端部署（分享给同事）

> **架构**：你本机跑 `generate.py` 生成 `data.json`，git push 到 GitHub，GitHub Pages 自动托管成公网 URL。同事用浏览器打开即可，不需要装任何东西。

### 一次性初始化（5 分钟）

#### 1. 在 GitHub 创建仓库

- 登录 [github.com](https://github.com) → New repository
- 仓库名建议：`mag7-options-dashboard`
- 选 **Public**（GitHub Pages 免费版只支持 Public 仓库；策略数据本身不敏感）
- **不要**勾选 Add README（避免和本地冲突）

#### 2. 开启 GitHub Pages

仓库页面 → **Settings** → **Pages**：
- Source：`Deploy from a branch`
- Branch：`main` / `(root)` → Save

约 1 分钟后页面顶部会显示访问 URL：
```
https://<你的GitHub用户名>.github.io/mag7-options-dashboard/
```

#### 3. 本地关联远程仓库

```bash
cd ~/options-dashboard
git init
git branch -M main
git remote add origin https://github.com/<你的GitHub用户名>/mag7-options-dashboard.git
git add .
git commit -m "initial commit"
git push -u origin main
```

> 第一次 push 会要求 GitHub 登录。建议用 [Personal Access Token](https://github.com/settings/tokens) 当密码（Token 配置一次后 Windows 凭据管理器会记住）。

### 日常刷新数据

每次想更新数据，双击 `deploy.bat`：
1. 调富途 API 重新生成 `data.json`
2. `git commit + push` 到 GitHub
3. GitHub Pages 约 1 分钟后部署完成

发同事的 URL 始终是：`https://<用户名>.github.io/mag7-options-dashboard/`

### 自动定时部署（可选）

让 Windows 计划任务每天美股开盘前自动跑一次 `deploy.bat`：

```
Win+R → taskschd.msc → 创建基本任务
名称：mag7 daily refresh
触发器：每天 21:15（北京时间，对应美股盘前）
操作：启动程序 → C:\Users\daisyzhang\options-dashboard\deploy.bat
```

---

## 三类策略

| 分类 | 触发条件 | 操作 |
|------|----------|------|
| **方向性** | 盘前涨跌 > 0.3% | 买 OTM Call/Put（Δ 0.25–0.50） |
| **IV/HV 卖方** | ATM IV / HV30 > 1.15 | 卖 OTM 信用价差（\|Δ\| 0.18–0.32） |
| **综合打分** | 流动性 + Theta 衰减效率 | 综合最优合约 |

## 文件

- `generate.py` — 数据生成（调富途 API）
- `index.html` — 前端页面（含小白入门、悬停术语解释、白话操作指引）
- `data.json` — 生成的策略数据
- `run.bat` / `refresh-loop.bat` — 本地一键启动
- `deploy.bat` — 一键推送到 GitHub Pages

## 风险提示

期权有归零风险，本工具是研究辅助，不构成投资建议。
