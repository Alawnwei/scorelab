# ⚽ 足球分析系统 — GitHub 部署操作手册

> **目标**：将代码+数据托管到 GitHub，用 GitHub Pages 手机查看看板，实现"笔记本跑预测→手机看结果"。

---

## 目录

- [第一步：注册/登录 GitHub](#第一步注册登录-github)
- [第二步：创建仓库](#第二步创建仓库)
- [第三步：本地 Git 配置](#第三步本地-git-配置)
- [第四步：推送代码到 GitHub](#第四步推送代码到-github)
- [第五步：启用 GitHub Pages](#第五步启用-github-pages)
- [第六步：验证看板](#第六步验证看板)
- [第七步：每日操作流](#第七步每日操作流)
- [第八步：设置通知（选做）](#第八步设置通知选做)
- [附录：常用命令速查](#附录常用命令速查)

---

## 第一步：注册/登录 GitHub

1. 打开 https://github.com
2. 点击右上角 **Sign up**
3. 填写用户名（建议全英文，如 `football-analyzer`）、邮箱、密码，完成验证
4. 登录后进入个人主页

> ✅ 已有账号则直接登录

---

## 第二步：创建仓库

1. 点击右上角 **+** → **New repository**

2. 填写仓库信息：

   | 字段 | 填写内容 |
   |:-----|:---------|
   | Repository name | `scorelab` |
   | Description | 选填，如 `足球预测分析系统` |
   | Public / Private | **Private**（你的赔率数据不建议公开） |
   | Initialize this repo with | ❌ **不勾选**（我们从本地推代码） |
   | Add .gitignore | None |
   | License | None |

3. 点击 **Create repository**

创建完成后会看到一个空仓库页面，显示 Git 地址：

```
https://github.com/你的用户名/scorelab.git
```

**把这个地址复制下来，下一步要用。**

---

## 第三步：本地 Git 配置

打开你的 Git Bash（在项目目录 `C:\Users\Huawei\Downloads\电商\足球分析` 里操作）：

```bash
# 1. 设置 Git 全局用户信息（仅首次需设置）
git config --global user.name "你的GitHub用户名"
git config --global user.email "你的GitHub邮箱"
```

```bash
# 2. 初始化本地仓库（如果还没初始化过）
cd "C:/Users/Huawei/Downloads/电商/scorelab"
git init
```

```bash
# 3. 创建 .gitignore 忽略不需要跟踪的文件
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "node_modules/" >> .gitignore
```

```bash
# 4. 添加远程仓库地址
git remote add origin https://github.com/你的用户名/scorelab.git
```

> ⚠️ 把 `你的用户名` 替换成你实际的 GitHub 用户名

**验证远程仓库配置成功**：
```bash
git remote -v
# 应该显示：
# origin  https://github.com/你的用户名/scorelab.git (fetch)
# origin  https://github.com/你的用户名/scorelab.git (push)
```

---

## 第四步：推送代码到 GitHub

首次推送（完整项目）：

```bash
# 1. 添加所有文件
git add -A

# 2. 首次提交
git commit -m "🎉 首次提交：足球预测系统 v8.4"

# 3. 推送到 GitHub
git push -u origin master
```

> 首次 push 会弹出 GitHub 登录窗口。
> GitHub 已于 2021 年 8 月移除了密码认证，推荐以下方式登录：
> - **方式 A（推荐）**：[GitHub CLI](https://cli.github.com/) — 安装后运行 `gh auth login`，按提示浏览器登录
> - **方式 B**：使用 Personal Access Token — GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token，勾选 `repo` 权限，生成的 token 作为密码使用
> - **方式 C**：SSH 密钥（更安全）— 参考[GitHub SSH 文档](https://docs.github.com/zh/authentication/connecting-to-github-with-ssh)

**切换为 SSH 方式（可选）**：
```bash
git remote set-url origin git@github.com:你的用户名/scorelab.git
```

**推送成功后**，刷新 GitHub 仓库页面，应该能看到所有代码文件了。

---

## 第五步：启用 GitHub Pages

GitHub Pages 免费托管 HTML 文件，手机也能访问。

### 方式 A：手动设置（推荐，兼容现有项目结构）

1. 打开仓库页面 → **Settings** → **Pages**

   ![GitHub Pages 入口](https://docs.github.com/assets/cb-10452/images/help/pages/pages-settings-page.png)

2. 在 **Branch** 区域：

   | 字段 | 填写内容 |
   |:-----|:---------|
   | Source | **Deploy from a branch** |
   | Branch | `master` |
   | Folder | `/html` |
   | 点击 **Save** |

3. 等待 1-2 分钟，页面顶部会显示访问地址：

   ```
   https://你的用户名.github.io/scorelab
   ```

> 💡 **GitHub Pages 的优势**：每次 `git push` 后 **自动重新部署**，无需手动点击更新！

### 方式 B：GitHub Actions（自动构建，适合未来扩展）

如果想在未来添加构建步骤（如 CSS 压缩、JS 打包），可以用 Actions 工作流。

在仓库中创建 `.github/workflows/deploy-pages.yml`：

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [master]

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: html/
      - name: Deploy to GitHub Pages
        uses: actions/deploy-pages@v4
```

然后用方式 A 的 Pages 设置选择 **GitHub Actions** 作为 source 即可。

> 如果你只需要托管静态 HTML，用 **方式 A** 最简单。

---

## 第六步：验证看板

先本地生成一次看板：

```bash
cd "C:/Users/Huawei/Downloads/电商/scorelab"
python skill/report_to_html.py
```

然后推送：

```bash
git add -A
git commit -m "📊 初始看板"
git push
```

等待 1-2 分钟让 GitHub Pages 自动部署，然后用手机打开：

```
https://你的用户名.github.io/scorelab/html/report.html
```

> 应该能看到：KPI 卡片 + 校准曲线 + 预测表格。

---

## 第七步：每日操作流

### 早上：开始工作

```bash
# 1. 拉取最新数据（如果之前有其他设备推送过）
git pull

# 2. 跑预测
python skill/predict.py --home "主队" --away "客队" --league wm26
```

### 预测后：更新看板并推送

```bash
# 3. 生成 HTML 看板
python skill/report_to_html.py

# 4. 推送到 GitHub
git add -A
git commit -m "📊 2026-07-08 预测更新"
git push
```

### 推送后：等待自动部署

GitHub Pages 会在推送后自动重新部署，通常 1-2 分钟生效。
可在仓库 **Actions** 选项卡查看部署进度。

### 手机上查看

手机浏览器打开：
```
https://你的用户名.github.io/scorelab/html/report.html
```

### 赛后：回填结果

```bash
# 自动回填
python skill/sync_results.py

# 复盘
python skill/auto_review.py --days 7

# 更新看板
python skill/report_to_html.py
git add -A && git commit -m "📊 赛后更新" && git push
```

### 一键脚本（推荐）

把以上流程写成 `deploy.sh`（用 Git Bash 运行）：

```bash
#!/bin/bash
# deploy.sh — 预测→看板→推送 一键完成

if [ $# -lt 2 ]; then
  echo "用法: bash deploy.sh <主队> <客队> [联赛]"
  exit 1
fi

HOME=$1
AWAY=$2
LEAGUE=${3:-wm26}

echo "🔮 预测: $HOME vs $AWAY ($LEAGUE)"
python skill/predict.py --home "$HOME" --away "$AWAY" --league "$LEAGUE"

echo "📊 生成看板..."
python skill/report_to_html.py

echo "🚀 推送 GitHub..."
git add -A
git commit -m "📊 $(date +%Y-%m-%d) $HOME vs $AWAY"
git push

echo "✅ 完成！等待 GitHub Pages 自动部署（约1-2分钟）"
echo "   https://你的用户名.github.io/scorelab/html/report.html"
```

用法：
```bash
bash deploy.sh "葡萄牙" "西班牙" wm26
```

---

## 第八步：设置通知（选做）

### 方案 A：GitHub 通知（最简单）

1. 打开仓库页面 → 点击 **Watch** → 选择 **All Activity**
2. 在 GitHub → Settings → Notifications，确认邮箱已绑定，开启 **Email** 通知
3. 手机安装邮箱 App，开启推送通知

效果：你每次 `git push` 后，手机会收到邮件通知。

### 方案 B：GitHub Actions 失败通知

如果使用 Actions 部署，可以在 Actions 设置中开启 **Email notifications** 只在失败时通知：

1. 仓库 → Settings → Notifications → **Actions**
2. 勾选 **Send notifications for failed workflows only**

### 方案 C：Windows 弹窗通知（预测完成提醒）

在 `deploy.sh` 末尾添加：

```bash
# Windows 弹窗
powershell -Command "& {Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('预测完成：$HOME vs $AWAY', '⚽ 足球分析')}"
```

---

## 附录：常用命令速查

### Git 日常

| 操作 | 命令 |
|:-----|:------|
| 拉取最新 | `git pull` |
| 查看状态 | `git status` |
| 添加所有变更 | `git add -A` |
| 提交 | `git commit -m "说明"` |
| 推送 | `git push` |
| 查看历史 | `git log --oneline --graph` |

### 系统操作

| 操作 | 命令 |
|:-----|:------|
| 预测 | `python skill/predict.py --home "A" --away "B" --league wm26` |
| 强制预测 | `python skill/predict.py --home "A" --away "B" --league wm26 --force` |
| 生成看板 | `python skill/report_to_html.py` |
| 赛后回填 | `python skill/sync_results.py` |
| 复盘 | `python skill/auto_review.py --days 7` |
| 准确率 | `python skill/accuracy_report.py` |
| 参数状态 | `python skill/update_calibration.py --params` |
| 校准 | `python skill/update_calibration.py --apply` |

### GitHub Pages 部署

推送后等待 1-2 分钟自动部署，可在仓库 **Actions** 选项卡查看进度：
```
https://github.com/你的用户名/scorelab/actions
```

---

> **📱 最终效果**：笔记本上跑 `bash deploy.sh "葡萄牙" "西班牙"` → 手机打开 https://你的用户名.github.io/scorelab/html/report.html 就能看到预测结果和校准曲线。
