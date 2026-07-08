# ⚽ 足球分析系统 — Gitee 部署操作手册

> **目标**：将代码+数据托管到 Gitee，用 Gitee Pages 手机查看看板，实现"笔记本跑预测→手机看结果"。

---

## 目录

- [第一步：注册/登录 Gitee](#第一步注册登录-gitee)
- [第二步：创建仓库](#第二步创建仓库)
- [第三步：本地 Git 配置](#第三步本地-git-配置)
- [第四步：推送代码到 Gitee](#第四步推送代码到-gitee)
- [第五步：启用 Gitee Pages](#第五步启用-gitee-pages)
- [第六步：验证看板](#第六步验证看板)
- [第七步：每日操作流](#第七步每日操作流)
- [第八步：设置通知（选做）](#第八步设置通知选做)
- [附录：常用命令速查](#附录常用命令速查)

---

## 第一步：注册/登录 Gitee

1. 打开 https://gitee.com
2. 点击右上角 **注册**
3. 填写用户名（建议全英文，如 `football-analyzer`）、邮箱、密码
4. 登录后进入个人主页

> ✅ 已有账号则直接登录

---

## 第二步：创建仓库

1. 点击右上角 **+** → **新建仓库**

2. 填写仓库信息：

   | 字段 | 填写内容 |
   |:-----|:---------|
   | 仓库名称 | `scorelab` |
   | 路径（Path） | 自动生成，不用改 |
   | 是否开源 | **私有**（你的赔率数据不建议公开） |
   | 初始化仓库 | ❌ **不勾选**（我们从本地推代码） |
   | 模板 | 不选 |
   | 分支模型 | 单分支（默认） |

3. 点击 **创建**

创建完成后会看到一个空仓库页面，显示 Git 地址：

```
https://gitee.com/你的用户名/scorelab.git
```

**把这个地址复制下来，下一步要用。**

---

## 第三步：本地 Git 配置

打开你的 Git Bash（在项目目录 `C:\Users\Huawei\Downloads\电商\足球分析` 里操作）：

```bash
# 1. 设置 Git 全局用户信息（仅首次需设置）
git config --global user.name "你的Gitee用户名"
git config --global user.email "你的Gitee邮箱"
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
git remote add origin https://gitee.com/你的用户名/scorelab.git
```

> ⚠️ 把 `你的用户名` 替换成你实际的 Gitee 用户名

**验证远程仓库配置成功**：
```bash
git remote -v
# 应该显示：
# origin  https://gitee.com/你的用户名/scorelab.git (fetch)
# origin  https://gitee.com/你的用户名/scorelab.git (push)
```

---

## 第四步：推送代码到 Gitee

首次推送（完整项目）：

```bash
# 1. 添加所有文件
git add -A

# 2. 首次提交
git commit -m "🎉 首次提交：足球预测系统 v8.4"

# 3. 推送到 Gitee
git push -u origin master
```

> 首次 push 会弹出 Gitee 登录窗口，输入用户名密码即可。
> 如果提示 `remote: [session-xx] Incorrect username or password`，去 Gitee → 设置 → 安全设置 → 私人令牌，生成一个 token 作为密码。

**推送成功后**，刷新 Gitee 仓库页面，应该能看到所有代码文件了。

---

## 第五步：启用 Gitee Pages

Gitee Pages 免费托管 HTML 文件，手机也能访问。

1. 打开仓库页面 → **服务** → **Gitee Pages**

   ![Gitee Pages 入口](https://gitee.com/assets/help/images/pages/pages.png)

2. 填写配置：

   | 字段 | 填写内容 |
   |:-----|:---------|
   | 部署分支 | `master` |
   | 部署目录 | `/html` |
   | 强制 HTTPS | ✅ 勾选 |

3. 点击 **启动**

4. 等待几秒钟，页面会显示访问地址：

   ```
   https://你的用户名.gitee.io/scorelab
   ```

**把这个地址收藏到手机浏览器书签。**

> ⚠️ **注意**：Gitee Pages 免费版每次 push 后需要手动点"更新"才会刷新。
> 每次 `git push` 后，回到这个页面点一下 **更新** 按钮。

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

去 Gitee Pages 页面点 **更新**，然后用手机打开：

```
https://你的用户名.gitee.io/scorelab/html/report.html
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

# 4. 推送到 Gitee
git add -A
git commit -m "📊 2026-07-08 预测更新"
git push
```

### 推送后：刷新 Pages

打开 https://gitee.com/你的用户名/scorelab/pages → 点 **更新**

### 手机上查看

手机浏览器打开：
```
https://你的用户名.gitee.io/scorelab/html/report.html
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

echo "🚀 推送 Gitee..."
git add -A
git commit -m "📊 $(date +%Y-%m-%d) $HOME vs $AWAY"
git push

echo "✅ 完成！去 Pages 点更新："
echo "   https://gitee.com/你的用户名/scorelab/pages"
```

用法：
```bash
bash deploy.sh "葡萄牙" "西班牙" wm26
```

---

## 第八步：设置通知（选做）

### 方案 A：Gitee 邮件通知（最简单）

每次 push 后自动发邮件到手机：

1. 打开仓库 → **Watch** → 点选 **所有活动**
2. 在 Gitee → 设置 → 个人资料 → 确认邮箱已绑定
3. 手机安装邮箱 App，开启推送通知

效果：你每次 `git push` 后，手机会收到邮件通知。

### 方案 B：Windows 弹窗通知（预测完成提醒）

在 `run_predict.sh` 末尾添加：

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

### Gitee Pages 更新

推送后去这个页面点 **更新**：
```
https://gitee.com/你的用户名/scorelab/pages
```

---

> **📱 最终效果**：笔记本上跑 `bash deploy.sh "葡萄牙" "西班牙"` → 手机打开 https://你的用户名.gitee.io/scorelab/html/report.html 就能看到预测结果和校准曲线。
