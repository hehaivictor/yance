# 研策 Yance

`研策（Yance）` 是一个本地单机版的专业学位论文开题智能参谋，Slogan 是“让开题更成体系”。当前默认面向武汉大学经济与管理学院专业硕士开题场景，并内置《武汉大学经济与管理学院专业硕士学位论文写作指南（2024年第二版）》作为学校写作要求，强调三件事：

- 题目推荐必须基于证据、导师方向和学校规则，而不是黑盒拼题
- 正文、PPT、讲稿必须从同一份冻结版报告派生
- 没有来源、未核验、字段冲突未处理的内容，不应该进入最终正文

## 目录结构

```text
backend/   FastAPI 后端，负责事实层 / 推理层 / 生成层
frontend/  Next.js 前端，提供以题目收敛和成果导出为主的开题界面
```

## 后端能力

- 工作区与学校规则管理
- 武汉大学开题写作指南自动入库
- 资料导入与字段抽取
- 公开信息联网补全
- 按需触发的访谈问题生成与回填
- 候选题五维评分
- 文献导入与公开元数据补全
- 报告草稿生成
- Word / PPT / 讲稿冻结导出

## 前端能力

- 以“基本信息 -> 题目收敛 -> 开题产出”为主流程
- 自动补全和系统校验默认下沉，不干扰主界面
- 候选题、报告草稿、冻结导出集中在同一条工作流内
- 可直接下载冻结版 Markdown / Word / PPT / 讲稿 / 来源快照

## 运行方式

### 一条命令启动

```bash
cd /Users/hehai/Documents/开目软件/Agents/project/Yance
bash ./scripts/dev.sh
```

这个脚本会：

- 自动检查 `backend/.venv` 和 `frontend/node_modules`
- 缺依赖时自动执行安装
- 同时启动后端 `http://127.0.0.1:8000`
- 同时启动前端 `http://127.0.0.1:3000`

按 `Ctrl+C` 会一起停止两个服务。

### 手动启动

### 1. 启动后端

```bash
cd /Users/hehai/Documents/开目软件/Agents/project/Yance/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认监听 `http://127.0.0.1:8000`

### 2. 启动前端

```bash
cd /Users/hehai/Documents/开目软件/Agents/project/Yance/frontend
npm install
npm run dev
```

### 仅安装依赖

```bash
cd /Users/hehai/Documents/开目软件/Agents/project/Yance
bash ./scripts/bootstrap.sh
```

默认监听 `http://127.0.0.1:3000`

### 前端自动验收

如果你想用 Playwright 自带的 Chromium 做页面自动检查，而不是依赖本机 Chrome，会话里直接执行：

```bash
cd /Users/hehai/Documents/开目软件/Agents/project/Yance
bash ./scripts/ui-smoke.sh
```

这个脚本会：

- 自动检查并安装前端依赖
- 自动安装 Playwright 的 Chromium 浏览器
- 优先复用现有的 `http://127.0.0.1:3000` 页面；如果没有，就在 `http://127.0.0.1:3100` 拉起一个临时前端服务
- 运行首页与四区导航的 smoke 检查
- 输出截图和验收结果到 `output/playwright/`

如果你想复用已经运行中的页面，可以先设定地址：

```bash
UI_SMOKE_BASE_URL=http://127.0.0.1:3000 bash ./scripts/ui-smoke.sh
```

## 可选环境变量

参考根目录的 `.env.example`。

- `OPENAI_API_KEY`：可选，配置后会启用题目候选生成和正文润色
- `OPENAI_BASE_URL`：可选，默认 `https://api.openai.com/v1`
- `OPENAI_MODEL`：可选，默认 `gpt-5-mini`
- `NEXT_PUBLIC_API_BASE_URL`：前端访问后端的地址，默认 `http://127.0.0.1:8000`

## 当前实现边界

- `v1` 不支持多租户和账号系统
- 武汉大学作为当前唯一学校入口，选择后即默认采用 2024 年第二版写作指南
- 中文文献优先通过用户后续补充的真实资料进入项目空间
- 英文文献会尝试用公开元数据补全，但不会编造字段
- 公开资料联网补全目前默认走网页搜索与页面抽取，不做需要登录的数据库自动化
