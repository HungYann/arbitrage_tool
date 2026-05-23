# Mintlify 文档部署指南

## 📚 什么是 Mintlify？

Mintlify 是一个现代文档框架，提供：
- 美观的文档网站
- 自动搜索功能
- API 文档集成（OpenAPI/Swagger）
- 深色/浅色模式
- 响应式设计
- 零配置部署

## 🔄 部署架构

```
Local Development
    ↓
    └→ npm run dev (http://localhost:3000)
    
Git Push
    ↓
GitHub Actions
    ↓
    ├→ npm install
    ├→ npm run broken-links (检查链接)
    ├→ 验证 Mintlify 输出目录
    └→ 上传到 GitHub Pages Artifact
    
GitHub Pages
    ↓
    Static HTML 服务
    ↓
https://hungyann.github.io/arbitrage_tool/
```

## ⚙️ 当前配置

### 工作流文件
- **文件**: `.github/workflows/deploy-docs.yml`
- **触发条件**: Push 到 main 分支 + mintlify-docs/ 文件变更
- **部署方式**: GitHub Actions → Static HTML
- **构建时间**: ~5 分钟

### 部署流程

```yaml
1. Checkout 代码
   ↓
2. 安装 Node.js 18 + npm 依赖
   ↓
3. 链接完整性检查（npm run broken-links）
   ↓
4. 准备 Mintlify 输出目录
   ↓
5. 上传 artifact 到 GitHub Pages
   ↓
6. 自动部署到 GitHub Pages
   ↓
7. 文档上线 ✅
```

## 🚀 本地开发工作流

### 启动开发服务器

```bash
cd mintlify-docs
npm install
npm run dev
```

访问 `http://localhost:3000` 查看实时更新

### 编辑文档

```
mintlify-docs/
├── docs.json              # 全局配置（导航、主题等）
├── index.mdx              # 首页
├── get-started/           # 快速开始
├── core-concepts/         # 核心概念
├── guides/                # 使用指南
├── reference/             # 参考文档
└── openapi.json          # API 文档
```

### 发布更改

```bash
git add mintlify-docs/
git commit -m "docs: update documentation"
git push origin main
# GitHub Actions 自动部署 → 2-5 分钟后上线
```

## 📊 监控部署

### 检查部署状态

1. GitHub 主页 → "Actions" 标签
2. 查找 "Deploy Mintlify Docs to GitHub Pages" 工作流
3. 点击最新的运行记录
4. 查看各步骤的日志

### 访问已部署的文档

```
https://hungyann.github.io/arbitrage_tool/
```

### 测试更新

部署完成后，访问上述 URL 并验证：
- ✅ 导航菜单加载
- ✅ 搜索功能正常
- ✅ API 文档显示
- ✅ 链接有效

## 🔧 常见问题

### Q: 文档没有更新？

**原因和解决**：
1. Check if workflow triggered
   ```bash
   git log --oneline -5
   # 确认 commit 已 push
   ```

2. 检查 GitHub Actions 日志
   - Actions → Deploy Mintlify Docs → 查看失败原因

3. 常见原因：
   - 链接检查失败（broken-links）
   - npm 依赖安装失败
   - 文件权限问题

### Q: 如何加速部署？

**已优化的方面**：
- ✅ npm 缓存（加快依赖安装）
- ✅ Node.js 18 LTS（最新稳定版）
- ✅ 只在 main push 时部署（减少不必要的运行）

**进一步优化**：
```yaml
# 如果构建很慢，可以跳过链接检查
npm run broken-links || echo "Skip on failure"
```

### Q: 如何回滚文档？

**Git 回滚**：
```bash
git revert <commit-hash>
git push origin main
# 工作流自动重新部署
```

### Q: 自定义域名部署

如果要使用自定义域名（如 `docs.example.com`）：

1. 在 DNS 记录中添加 CNAME
   ```
   docs.example.com CNAME hungyann.github.io
   ```

2. GitHub Settings → Pages → Custom domain
   ```
   输入：docs.example.com
   ```

3. GitHub 自动创建 CNAME 文件
4. 等待 DNS 传播（通常 24 小时内）

### Q: 如何禁用特定文档页面？

编辑 `mintlify-docs/docs.json`，从 `navigation` 中移除对应页面：

```json
{
  "navigation": [
    {
      "group": "Get Started",
      "pages": [
        "index",
        "get-started/quickstart"
        // "get-started/onboarding"  ← 注释掉即隐藏
      ]
    }
  ]
}
```

## 📝 最佳实践

### 1. 频繁小更新而不是大批量更新

```bash
# 好 ✅
git commit -m "docs: add API endpoint documentation"
git push

# 不好 ❌
git commit -m "docs: update everything"
```

### 2. 本地验证后再 push

```bash
# 启动本地开发服务器
npm run dev

# 检查链接
npm run broken-links

# 然后再 push
git push
```

### 3. 保持导航结构清晰

```
docs.json 中的 navigation 应该对应实际的文件结构
├── index → index.mdx
├── guides/overview → guides/overview.mdx
└── reference/api → reference/api.mdx
```

### 4. 图片和资源

将资源放在 `assets/` 目录：
```
mintlify-docs/assets/
├── images/
├── logos/
└── icons/
```

在文档中引用：
```markdown
![Architecture](../../assets/images/architecture.png)
```

## 🔗 相关文档

- [Mintlify 官方文档](https://mintlify.com/docs)
- [Mintlify 部署指南](https://mintlify.com/docs/deployment/overview)
- [GitHub Pages 文档](https://docs.github.com/en/pages)
- [GitHub Actions 文档](https://docs.github.com/en/actions)

## ✅ 发布清单

新增文档后：

- [ ] 在本地 `npm run dev` 测试
- [ ] 运行 `npm run broken-links` 检查链接
- [ ] 更新 `docs.json` 导航
- [ ] Commit 和 push
- [ ] 检查 GitHub Actions 部署状态
- [ ] 访问 https://hungyann.github.io/arbitrage_tool/ 验证
- [ ] 检查搜索功能
- [ ] 确认所有链接有效

---

**部署问题?** → 查看 GitHub Actions 日志或创建 Issue
