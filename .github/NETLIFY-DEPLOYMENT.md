# Netlify 部署指南

## 📋 概述

将 Mintlify 文档部署到 Netlify，获得完整的 Mintlify 功能（搜索、导航、API 文档等）。

---

## 🚀 部署步骤（5 分钟）

### **第1步：注册 Netlify**

1. 访问 https://netlify.com
2. 点击 **"Sign up"**
3. 选择 **"Sign up with GitHub"**
4. 授权 Netlify 访问你的 GitHub 账户

### **第2步：创建新项目**

1. 登录 Netlify Dashboard
2. 点击 **"Add new site"**
3. 选择 **"Import an existing project"**
4. 找到并选择 `HungYann/arbitrage_tool`

### **第3步：配置构建设置**

Netlify 会自动检测 `netlify.toml` 文件，应该显示：

```
Build command: cd mintlify-docs && npm install && npm run dev
Publish directory: mintlify-docs
Node version: 18.17.0
```

如果没有自动填充，手动输入上述设置。

### **第4步：部署**

1. 点击 **"Deploy site"**
2. 等待部署完成（通常 3-5 分钟）
3. 获得你的 Netlify URL，例如：
   ```
   https://arbitrage-tool-xxx.netlify.app
   ```

### **第5步：自定义域名（可选）**

1. 在 Netlify Dashboard → **Site settings** → **Domain management**
2. 点击 **"Add custom domain"**
3. 输入你的域名（如 `docs.example.com`）
4. 按说明配置 DNS

---

## ✅ 验证部署

部署完成后，访问你的 Netlify URL：

- ✅ 首页加载正确
- ✅ 导航菜单可点击
- ✅ **搜索功能工作**
- ✅ API 文档显示
- ✅ 深色/浅色模式可切换
- ✅ 所有链接有效

---

## 🔄 自动部署

配置完成后，每次 push 到 main 分支（修改 `mintlify-docs/**`）时，Netlify 会自动：

1. ✅ 拉取最新代码
2. ✅ 安装依赖
3. ✅ 运行 `npm run dev`
4. ✅ 构建和部署 Mintlify

部署日志可在 **Netlify Dashboard** → **Deploys** 中查看。

---

## 📁 配置文件详解

### `netlify.toml`

```toml
[build]
command = "cd mintlify-docs && npm install && npm run dev"
publish = "mintlify-docs"
NODE_VERSION = "18.17.0"

[build.environment]
PUPPETEER_SKIP_DOWNLOAD = "true"
PUPPETEER_SKIP_CHROMIUM_DOWNLOAD = "true"
```

**参数说明**：
- `command`: 构建命令
- `publish`: 发布目录（Netlify 服务这个目录）
- `NODE_VERSION`: Node.js 版本
- `PUPPETEER_SKIP_*`: 跳过 Puppeteer 下载，加快构建

---

## 🎯 部署架构

```
GitHub 仓库 (main 分支)
    ├── mintlify-docs/          ← 文档源
    │   ├── docs.json
    │   ├── index.mdx
    │   ├── package.json
    │   └── ...
    │
    └── netlify.toml            ← Netlify 配置

            ↓

        Netlify 部署
            ↓
    https://arbitrage-tool-xxx.netlify.app
            ↓
    完整的 Mintlify 网站
    ✅ 搜索功能
    ✅ 导航菜单
    ✅ API 文档
    ✅ 深色/浅色模式
    ✅ 响应式设计
```

---

## 🛠️ 常见问题

### Q: 构建失败怎么办？

**A**: 检查 Netlify 构建日志：
1. Netlify Dashboard → **Deploys**
2. 点击失败的构建
3. 查看 **Deploy log** 了解错误

常见原因：
- Node 版本不兼容（需要 18+）
- npm 依赖安装失败
- Mintlify 需要特定的包版本

**解决方案**：
```bash
# 本地测试构建
cd mintlify-docs
npm install
npm run dev
```

### Q: 如何更新部署？

**A**: 只需 push 到 main 分支：
```bash
git add mintlify-docs/
git commit -m "docs: update documentation"
git push origin main
```

Netlify 会自动检测变更并重新部署。

### Q: 如何回滚到之前的版本？

**A**: 
1. Netlify Dashboard → **Deploys**
2. 找到要回滚的版本
3. 点击 **...** → **Publish deploy**

### Q: 能否同时在 GitHub Pages 和 Netlify 部署？

**A**: 可以！两个平台互不冲突：
- **GitHub Pages**: https://hungyann.github.io/arbitrage_tool/
- **Netlify**: https://arbitrage-tool-xxx.netlify.app/

---

## 🔗 相关资源

- [Netlify 官方文档](https://docs.netlify.com)
- [Netlify GitHub 集成](https://docs.netlify.com/configure-builds/repo-permissions-linking)
- [Mintlify 部署指南](https://mintlify.com/docs/deployment/overview)

---

## ✨ Netlify 的优势

| 功能 | GitHub Pages | Vercel | Netlify |
|------|-------------|--------|---------|
| 部署简单性 | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Mintlify 支持 | ❌ | ⚠️ | ✅ 完整 |
| 自动部署 | ✅ | ✅ | ✅ |
| 性能 | 中等 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 搜索功能 | ❌ | ❌ | ✅ 内置 |
| 自定义域名 | ✅ | ✅ | ✅ |
| 构建日志 | 有限 | 详细 | 详细 |
| 免费套餐 | ✅ | ✅ | ✅ |

---

## 📝 部署检查清单

- [ ] 在 Netlify 上创建账户
- [ ] 连接 GitHub 仓库
- [ ] 配置构建设置（应自动识别 netlify.toml）
- [ ] 点击 Deploy
- [ ] 等待部署完成（3-5 分钟）
- [ ] 访问 Netlify URL 验证
- [ ] 测试搜索功能
- [ ] 测试导航菜单
- [ ] 测试深色/浅色模式
- [ ] 验证 API 文档加载

---

**部署完成！你现在拥有一个完整功能的 Mintlify 文档网站！** 🎉
