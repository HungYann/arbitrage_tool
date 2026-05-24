# Vercel 部署指南

## 📋 概述

将 Mintlify 文档部署到 Vercel，获得更好的构建支持和性能。

## 🚀 部署步骤

### 第1步：在 Vercel 上创建账户和项目

1. 访问 [Vercel](https://vercel.com) 并使用 GitHub 账户登录
2. 点击 **"New Project"**
3. 选择你的 GitHub 仓库 `HungYann/arbitrage_tool`
4. 点击 **"Import"**

### 第2步：配置项目设置

在 **Project Settings** 中配置：

#### Framework Preset
- 选择：**Other**（Mintlify 不需要特定框架）

#### Build Settings
```
Build Command: cd mintlify-docs && npm install && npm run dev
Output Directory: mintlify-docs
Install Command: npm install --no-audit --no-fund
```

#### Environment Variables
添加以下环境变量：
```
PUPPETEER_SKIP_DOWNLOAD = true
PUPPETEER_SKIP_CHROMIUM_DOWNLOAD = true
NODE_VERSION = 18.17.0
```

### 第3步：部署

1. 点击 **"Deploy"** 按钮
2. 等待部署完成（通常 2-5 分钟）
3. 访问你的文档：`https://arbitrage-tool.vercel.app`

---

## 🔄 自动部署

配置后，每次 push 到 `main` 分支（修改 `mintlify-docs/` 文件夹）时，Vercel 会自动：
1. ✅ 拉取最新代码
2. ✅ 安装依赖
3. ✅ 构建文档
4. ✅ 部署到生产环境

---

## 🎯 部署配置详解

### vercel.json 文件

```json
{
  "buildCommand": "cd mintlify-docs && npm install && npm run build",
  "outputDirectory": "mintlify-docs",
  "installCommand": "npm install --no-audit --no-fund",
  "env": {
    "PUPPETEER_SKIP_DOWNLOAD": "true",
    "PUPPETEER_SKIP_CHROMIUM_DOWNLOAD": "true",
    "NODE_VERSION": "18.17.0"
  }
}
```

**参数说明**：
- `buildCommand`: 构建命令
- `outputDirectory`: 输出目录（Vercel 会提供此目录的内容）
- `installCommand`: 安装依赖命令
- `env`: 环境变量（跳过 Puppeteer 下载以加快构建）

---

## 📊 部署架构

```
GitHub 仓库 (main 分支)
    ├── mintlify-docs/          ← 源文件
    │   ├── docs.json
    │   ├── index.mdx
    │   ├── package.json
    │   └── ...
    │
    └── .github/workflows/      ← GitHub Actions
        └── deploy-docs.yml     ← （可选）同时部署到 GitHub Pages

                ↓

            Vercel 部署
                ↓
    https://arbitrage-tool.vercel.app
                ↓
    Mintlify 自动生成的网站
    ✅ 搜索功能
    ✅ 导航菜单
    ✅ API 文档集成
    ✅ 深色/浅色模式
```

---

## 🔗 自定义域名（可选）

如果要使用自定义域名（如 `docs.example.com`）：

### Vercel 配置

1. 在 Vercel 项目设置 → **Domains**
2. 点击 **"Add Domain"**
3. 输入你的域名（如 `docs.example.com`）
4. 按照说明配置 DNS 记录

### DNS 配置

在你的域名注册商（如 Namecheap、GoDaddy 等）添加：

```
Type: CNAME
Name: docs
Value: cname.vercel-dns.com.
```

---

## ✅ 验证部署

部署完成后，检查：

- [ ] 访问 Vercel 生成的 URL
- [ ] 导航菜单正确显示
- [ ] 搜索功能可用
- [ ] API 文档加载正常
- [ ] 深色/浅色模式切换正常
- [ ] 所有内部链接有效

---

## 🚨 常见问题

### Q: 构建失败怎么办？

**A**: 检查 Vercel 构建日志：
1. Vercel Dashboard → 你的项目 → **Deployments**
2. 点击失败的部署
3. 查看 **Build Logs** 了解错误原因

常见原因：
- Node 版本不兼容（需要 18+）
- npm 依赖安装失败（检查 `package.json` 中的依赖）
- Puppeteer 下载超时（已禁用）

### Q: 如何回滚到之前的版本？

**A**: 在 Vercel Deployments 页面找到之前的部署，点击 **"Promote to Production"**

### Q: 能否同时部署到 GitHub Pages 和 Vercel？

**A**: 可以！两个部署方式互不冲突。如果需要：
- GitHub Pages: https://hungyann.github.io/arbitrage_tool/
- Vercel: https://arbitrage-tool.vercel.app/

---

## 🌍 部署检查清单

在生产环境正式使用前，确保：

- [ ] 所有文档正确显示
- [ ] 搜索功能工作正常
- [ ] API 文档完整
- [ ] 响应式设计正常（移动端、平板、桌面）
- [ ] 性能满足要求（Lighthouse 评分 > 90）
- [ ] 没有 404 错误
- [ ] 链接都能正确跳转

---

## 📞 后续支持

如果遇到问题，可以：
1. 查看 [Vercel 官方文档](https://vercel.com/docs)
2. 查看 [Mintlify 部署指南](https://mintlify.com/docs/deployment/overview)
3. 提交 GitHub Issue

---

**部署完成后，你就拥有了一个专业的、自动更新的文档网站！** 🎉
