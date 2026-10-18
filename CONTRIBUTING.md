# 贡献指南 (Contributing Guide)

感谢你关注并愿意为本项目贡献代码！为了让协作更加高效，请在提交代码前仔细阅读以下指引。

---

## 🚀 提交流程 (Workflow)

我们推荐使用标准的 **Fork & Pull Request** 工作流：

1. **Fork 仓库**
   - 点击 GitHub 仓库右上角的 **Fork** 按钮，将仓库复制到你的个人 GitHub 账号下。

2. **克隆到本地**
   ```bash
   git clone https://github.com/<你的用户名>/leek.git
   cd leek
   ```

3. **关联上游仓库 (Upstream)**
   ```bash
   git remote add upstream https://github.com/EndlessJour9527/leek.git
   git fetch upstream
   ```

4. **创建开发分支**
   - 请基于最新的 `upstream/main` 创建新分支：
   ```bash
   git checkout -b feat/my-new-feature
   # 或修复 bug:
   git checkout -b fix/issue-description
   ```

5. **编写代码与测试**
   - 保持代码整洁，遵循项目规范。
   - 确保修改通过本地测试验证。

6. **提交 Commit**
   - 编写清晰、有意义的 Commit 信息。推荐使用 Conventional Commits 格式：
     - `feat: 添加新特性`
     - `fix: 修复某问题`
     - `docs: 更新文档`
     - `refactor: 重构代码`
     - `test: 增加或修改测试`

7. **推送分支并发起 Pull Request**
   ```bash
   git push origin feat/my-new-feature
   ```
   - 访问 GitHub 仓库页面，点击 **Compare & pull request**。
   - 按照 PR 模板详细填写变更内容和关联的 Issue。

---

## 📌 代码审查与合并 (Code Review & Merge)

- 维护者会对你的 PR 进行 Code Review，并可能会提出修改建议。
- 如果需要补充修改，请直接在该分支上追加 commit 并 push，PR 会自动更新。
- 审核通过后，维护者会将分支合并到 `main`。

再次感谢你的贡献！
