# CI/CD Pipeline 指南

## 概述

本项目使用 GitHub Actions 自动化以下任务：

| 工作流 | 触发条件 | 功能 |
|-------|--------|------|
| `ci.yml` | Push/PR main/develop | 代码质量、测试、构建、安全扫描 |
| `deploy-docs.yml` | Push main (mintlify-docs 变更) | 构建并部署文档到 GitHub Pages |

---

## 📋 CI/CD 流程详解

### 1. 代码质量检查 (Quality)
- **Flake8**: 语法和风格检查
- **Black**: 代码格式化检查
- **isort**: Import 排序检查

### 2. 单元测试 (Test)
- 在 Python 3.10, 3.11, 3.12 上运行测试
- 生成代码覆盖率报告
- 上传到 Codecov

### 3. Docker 构建 (Docker)
- 仅在 main 分支 push 时执行
- 构建 Docker 镜像（不推送）
- 缓存优化加速构建

### 4. 安全扫描 (Security)
- **Bandit**: Python 代码安全扫描
- **Safety**: 依赖漏洞检查
- **TruffleHog**: 敏感信息泄露检测

### 5. 文档构建 (Docs)
- 检查 Mintlify 文档链接
- 构建文档（可选）

---

## 🚀 GitHub Pages 部署配置（Static HTML）

### 部署方式说明

本项目使用 **Static HTML** 部署方式（而非 Jekyll）：
- ✅ 直接部署 Mintlify 生成的静态文件
- ✅ 无额外编译，部署速度快（5分钟内）
- ✅ 完全兼容 Mintlify 的设计和交互

### 第一步：启用 GitHub Pages

1. 访问仓库 Settings → Pages
2. **Source** 选择：`GitHub Actions`（不选 Jekyll）
3. 保存配置

### 第二步：验证部署

1. Push 到 main 分支（或修改 `mintlify-docs/**` 文件）
2. 在 Actions 标签查看 `deploy-docs` 工作流
3. 构建成功后，文档自动部署到：
   ```
   https://HungYann.github.io/arbitrage_tool/
   ```

### 第三步：自定义域名（可选）

如果你拥有自定义域名：

1. GitHub Settings → Pages → Custom domain
2. 输入你的域名（例如 `docs.example.com`）
3. 在域名注册商配置 CNAME 记录指向 `hungyann.github.io`

---

## 🛠️ 本地开发工作流

### 安装本地开发工具

```bash
# Python 工具
pip install black isort flake8 bandit

# 或使用 pre-commit hooks（推荐）
pip install pre-commit
pre-commit install
```

### 本地代码检查

```bash
# 格式化代码
black app tests
isort app tests

# 检查代码风格
flake8 app tests

# 运行测试
pytest tests/ -v --cov=app

# 安全扫描
bandit -r app
```

### 本地运行 Mintlify Docs

```bash
cd mintlify-docs
npm install
npm run dev
# 访问 http://localhost:3000
```

---

## 📊 CI/CD 状态检查

### 查看工作流状态

- 主页面：Repo → "Actions" 标签
- 分支保护：Settings → Branches → Branch protection rules
  - 要求 CI 通过才能 merge PR

### 设置分支保护规则

1. Settings → Branches
2. Add rule
3. Branch name pattern: `main`
4. 启用：
   - ✅ Require a pull request before merging
   - ✅ Require status checks to pass
   - ✅ Require branches to be up to date

---

## 🔐 Secret 管理

### 添加 GitHub Secret

如果 CI/CD 需要 secret（API密钥等）：

1. Settings → Secrets and variables → Actions
2. New repository secret
3. 在工作流中使用：
   ```yaml
   - name: Deploy
     env:
       API_KEY: ${{ secrets.API_KEY }}
     run: ./deploy.sh
   ```

**当前配置**：无需 secret（只用于公开部署）

---

## 📈 性能优化

### 缓存策略

- Node.js 依赖缓存（npm）
- Python 依赖缓存（pip）
- Docker 层缓存（buildx）

这大幅加快了 CI/CD 速度。

### 典型运行时间

- **Code Quality**: ~2 分钟
- **Tests (3 versions)**: ~4 分钟
- **Docker Build**: ~3 分钟
- **Security**: ~2 分钟
- **Docs Build**: ~1 分钟
- **总计**: ~10-12 分钟

---

## 🚨 常见问题

### Q: 文档没有部署？
**A**: 
1. 确保修改了 `mintlify-docs/` 下的文件
2. 检查 Actions 中 `deploy-docs` 的日志
3. 确认 GitHub Pages 已在 Settings 中启用

### Q: 测试失败怎么办？
**A**:
1. 查看 CI 日志了解具体错误
2. 本地运行 `pytest` 重现问题
3. 修复后重新 push

### Q: 如何跳过 CI？
**A**: **不推荐**，但如果需要：
```bash
git commit -m "your message [skip ci]"
```

### Q: 如何更新依赖版本？
**A**:
1. 编辑 `requirements.txt` 或 `package.json`
2. Push 后 CI 自动测试新版本
3. 如果失败，更新代码兼容性

---

## 📚 相关文档

- [GitHub Actions 官方文档](https://docs.github.com/en/actions)
- [GitHub Pages 官方文档](https://docs.github.com/en/pages)
- [Mintlify 部署文档](https://mintlify.com/docs/deployment/overview)

---

## ✅ 检查清单

发布新版本前：

- [ ] 本地所有测试通过
- [ ] 代码格式化正确（black, isort）
- [ ] 无 flake8 警告
- [ ] Bandit 安全扫描通过
- [ ] Mintlify 文档链接完整
- [ ] PR 通过 CI/CD 检查
- [ ] Merge 到 main 分支
- [ ] GitHub Pages 自动部署完成

---

**问题反馈** → GitHub Issues
