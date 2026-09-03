# 信息技术组卷台（前后端分离版）

把原来的单文件 HTML 拆成：Vue 3 前端 + FastAPI 后端 + MySQL 数据库。
题库进数据库、教师账号登录、Excel 模板上传由后端解析入库，题目改一次全校都看到。

原页面里的**均衡抽题算法**和**Excel 校验规则**是原样移植过来的，行为一致，不是重新设计。

> 想知道每个文件分别是干什么的、改功能该动哪里 → 看 [docs/项目结构.md](docs/项目结构.md)

---

## 一、目录结构

```
exam-system/
├─ 一键启动.bat              Windows 上双击就能跑（装依赖、建库、导题、开服务）
├─ 一键停止.bat              停掉前后端（只杀 python/node，不误伤别的程序）
├─ scripts/                  上面两个脚本调用的子脚本
├─ docker-compose.yml        服务器部署用：数据库 / 后端 / 前端 三个容器
├─ .env.example              端口、密码、密钥，复制成 .env 再改
├─ backup/backup.sh          每天备份数据库和上传目录
├─ legacy/信息技术组卷台.html   原来的单文件版本，存档 + 迁移数据源
│
├─ backend/                  Python FastAPI
│  ├─ app/
│  │  ├─ main.py             入口，挂载路由和 /uploads 静态目录
│  │  ├─ config.py           所有配置从环境变量读
│  │  ├─ database.py         数据库连接
│  │  ├─ models.py           7 张表的定义
│  │  ├─ schemas.py          接口出入参
│  │  ├─ security.py         bcrypt 密码哈希 + JWT 签发
│  │  ├─ deps.py             登录校验、管理员校验
│  │  ├─ constants.py        十类知识范围等种子数据
│  │  ├─ seed.py             首次启动建管理员、灌字典
│  │  ├─ services/
│  │  │  ├─ importer.py      Excel/CSV 解析与逐行校验（原 handleRows）
│  │  │  ├─ sampler.py       均衡抽题（原 allocate / pick）
│  │  │  ├─ paper.py         组卷：打乱选项、答案跟随、分大题、卷号
│  │  │  └─ export.py        题库/试卷 Excel、学生答题网页
│  │  └─ routers/            auth / dicts / questions / imports / papers
│  ├─ alembic/               表结构迁移脚本
│  ├─ tools/migrate_from_html.py   把老 HTML 里的题搬进数据库
│  └─ tests/                 test_logic.py 核心逻辑 + test_api.py 接口端到端
│
└─ frontend/                 Vue 3 + Vite + Element Plus
   └─ src/views/             Login / Paper（组卷）/ Questions（题库）/ Import（导入）
                             Exams（考试）/ Users（账号）/ Take（学生答题，免登录）
```

---

## 二、跑起来

### 方式 A：Windows 上双击运行（自己电脑试用、备课时用这个）

双击项目根目录的 **`一键启动.bat`**。它会自己做完这些事：

1. 检查 Python（要 3.10 以上）和 Node.js，缺了会直接告诉你去哪儿装；
2. 建 Python 虚拟环境、装后端依赖；
3. 建库、建管理员账号、灌知识范围字典；
4. 首次运行时把 `legacy/` 里那份 HTML 的题目和图片导进数据库；
5. 装前端依赖；
6. 起前后端两个服务，浏览器自动打开 `http://localhost:5173`。

第一次要联网装依赖，三到五分钟；以后再启动十几秒。
默认账号见 `backend\.env` 里的 `ADMIN_USERNAME` / `ADMIN_PASSWORD`（默认 `admin` / `admin123`，**登录后立刻改**）。

停止服务：关掉弹出的两个黑窗口，或者双击 `一键停止.bat`。

这种方式用的是 SQLite，数据在 `backend\data\app.db`，不需要装 MySQL 和 Docker。
适合一个人用；要给全校用，走下面的方式 B。

**可能遇到的两个问题**

- `npm error ECONNREFUSED 127.0.0.1:33210` —— npm 配了代理但代理软件没开。把代理开起来，或者清掉配置：
  `npm config delete proxy` 和 `npm config delete https-proxy`。
- 端口 8000 或 5173 被别的程序占了 —— 先用 `netstat -ano | findstr :8000` 看是谁。
  换端口不用改代码：后端启动时加 `--port 8001`，前端启动前设一个环境变量即可：

  ```bash
  set VITE_API_TARGET=http://127.0.0.1:8001 && npm run dev
  ```

  （`VITE_PORT` 同理，用来换前端自己的端口。）

### 方式 B：Docker 部署（服务器上用这个）

```bash
cp .env.example .env
```

改 `.env` 里的三处：`MYSQL_PASSWORD`、`JWT_SECRET`、`ADMIN_PASSWORD`。然后：

```bash
docker compose up -d --build
```

浏览器打开 `http://服务器IP:8080`，用 `.env` 里的管理员账号登录。
后端接口文档在 `http://服务器IP:8080/docs`（本地开发时是 `http://127.0.0.1:8000/docs`）。

### 方式 C：手工启动（改代码时用这个）

后端，用 SQLite，不需要装 MySQL：

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload
```

前端另开一个终端：

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`，Vite 会把 `/api` 代理到 8000 端口。

### 把老题库搬进来

`一键启动.bat` 首次运行时已经自动做过了。要手工再跑：

```bash
cd backend
python -m tools.migrate_from_html
```

不带参数就读 `legacy/信息技术组卷台.html`，也可以在后面指定别的文件路径。

实测结果：原文件 341 道题，其中 **10 道题干重复**被自动跳过，实际入库 **331 题**，
26 张 base64 图片落成 `data/uploads/images/*.png` 文件，数据库里只存路径。
去重按题干哈希（忽略空白差异），重复执行不会灌进重复数据。

---

## 三、功能一览

组卷页：

- 卷头填标题、学校、考试时长，卷号自动生成（`NO.12345`）
- 三种模式切换：**试卷**（学生用）/ **答案卷**（选择判断答案排成格子、操作题列要点）/ **在线自测**（直接在页面上作答，交卷自动判分）
- **打乱选择题的选项顺序**，正确答案自动跟着换，防止同桌抄
- 跳过原卷未给答案的题、必出题优先、按知识范围限定、随机种子（同种子出同一套卷）
- **换一批**：同样的条件重新抽
- 打印 / 存 PDF、**导出学生答题网页**、**导出本卷 Excel**
- 试卷可存档，历史试卷重新打开时选项顺序和当初印出去的一模一样

题库页：按题干关键字、题型、知识范围、来源筛选，只看必出题；点图片放大；
导出完整题库 / 只导出我补充的题 / 按当前筛选条件导出。

导入页：xlsx 和 csv 都能传（CSV 的 GBK 编码自动识别），逐行校验、失败原因带行号、题干查重。

界面：深色 / 浅色切换，记在本机。

考试页（正式考试）：把存档的试卷发布成考试，学生凭链接作答，**判分在服务器上做**。

- 学生**不需要账号**，打开 `/take/<口令>` 填姓名班级学号就能答
- **题目发给学生时不带答案** —— 取卷接口从结构上就没有 answer 字段，判分只在后端进行
- 四个开关：开放 / 交卷看分数 / 交卷看答案 / 允许重考（正式考试建议只开前两个）
- 同一学号默认只能交一次
- 成绩自动汇总：交卷数、均分、最高最低、每个学生的得分与答卷明细
- 「错得最多的题」直接列出来，讲评时用
- 导出成绩 Excel 三张表：成绩汇总 / 每题正确率分析 / 操作题原文（供人工评阅）

## 两种给学生用的方式，怎么选

| | 导出学生答题网页 | 发布考试 |
|---|---|---|
| 判分在哪 | 学生浏览器 | 服务器 |
| 答案位置 | **内嵌在网页源码里，学生能看到** | 只在服务器，学生拿不到 |
| 成绩收集 | 学生自己导出成绩单再交给老师 | 自动汇总，导出 Excel |
| 需要联网 | 不需要，文件发过去就行 | 需要能访问本系统 |
| 适合 | 课后练习、自测、发到 GitHub Pages | **正式考试、随堂测验** |

## 四、数据库表

| 表 | 存什么 |
|---|---|
| `users` | 账号、bcrypt 密码哈希、姓名、角色（admin/teacher）、是否停用 |
| `dict_items` | 知识范围、题型两类枚举。**加一类新范围只改这张表，不改代码** |
| `questions` | 题型、题干、答案、知识范围、来源、图片路径、必出标记、软删除标记、题干哈希（查重） |
| `options` | 题目的 A/B/C/D 选项，随题目级联删除 |
| `papers` / `paper_items` | 保存下来的试卷、题目顺序、打乱后的选项快照 |
| `exams` | 发布出去的考试：口令、开放状态、四个开关 |
| `exam_submissions` | 学生答卷：原始作答、判分明细、得分 |
| `import_logs` | 谁、什么时候、导了哪个文件、成功失败各几条、原件存到哪 |

两个刻意的设计：题目**软删除**（`is_deleted` 标记），误删能恢复；图片**存文件不存 base64**，数据库不会被撑爆。

---

## 五、接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | 登录，返回 JWT |
| GET | `/api/auth/me` | 当前登录人 |
| POST | `/api/auth/password` | 改自己的密码 |
| GET/POST/DELETE | `/api/auth/users` | 教师账号管理（管理员） |
| GET/POST | `/api/dicts` | 知识范围、题型清单 |
| GET | `/api/questions` | 题库分页查询（关键字/题型/范围过滤） |
| GET | `/api/questions/stats` | 题库概况 |
| POST/PUT/DELETE | `/api/questions` | 增改删（删是软删除） |
| POST | `/api/questions/upload-image` | 上传配图，返回 URL |
| GET | `/api/imports/template` | 下载空白 Excel 模板 |
| POST | `/api/imports/questions` | **上传模板文件 → 解析 → 校验 → 入库** |
| GET | `/api/imports/logs` | 导入记录 |
| GET | `/api/questions/export.xlsx` | 导出题库 Excel，支持全部筛选条件 |
| POST | `/api/papers/preview-plan` | 只算名额分布，不抽题 |
| POST | `/api/papers/generate` | 均衡抽题组卷，含打乱选项、卷头、分组 |
| POST | `/api/papers/export/xlsx` | 导出本卷 Excel |
| POST | `/api/papers/export/student-html` | **导出学生答题网页**（单文件，可直接分发） |
| GET/DELETE | `/api/papers` | 历史试卷 |
| POST/GET/PATCH/DELETE | `/api/exams` | 发布考试、开关、删除 |
| GET | `/api/exams/{id}/submissions` | 成绩列表与单份答卷明细 |
| GET | `/api/exams/{id}/stats` | 每题正确率分析 |
| GET | `/api/exams/{id}/export.xlsx` | 成绩汇总导出（三张表） |
| GET | `/api/take/{token}` | **学生取卷，公开访问，不含答案** |
| POST | `/api/take/{token}/submit` | **学生交卷，后端判分** |

接口文档是 FastAPI 自动生成的，改了接口文档自动跟着变，不用另写一份。

### 模板上传的完整链路

1. 前端把 `.xlsx` 传到 `POST /api/imports/questions`，请求头带 JWT；
2. 后端 openpyxl 逐行读，多张工作表一起读；
3. 按原页面同一套规则校验：题型能否识别、知识范围是否在十类之内、判断题答案归一成 正确/错误、选项拆成 A/B/C/D、选择题答案必须落在选项里；
4. 题干哈希去重，和库里已有题重复的自动跳过；
5. 合格的写进 `questions` + `options`，原件存一份到 `data/uploads/imports/`，结果记进 `import_logs`；
6. 返回 `{总行数, 成功, 失败, 重复跳过, 各题型条数, 失败明细[工作表, 行号, 原因]}`；
7. 前端展示结果表格，题库页刷新即可看到新题，组卷马上能抽到。

---

## 六、后期维护与更新

**改代码**：Git 管起来；接口文档自动生成；改表结构一律写 Alembic 迁移脚本，不手工改表：

```bash
cd backend
alembic revision --autogenerate -m "给题目加难度字段"
alembic upgrade head
```

容器下次启动会自动 `alembic upgrade head`，服务器上不用手动执行。

**改测试**：动了抽题策略、导入规则或接口，先跑测试：

```bash
cd backend && pytest -v
```

64 个用例，分三块：`test_logic.py` 管抽题算法、打乱选项、Excel/CSV 校验的边界；
`test_api.py` 用 FastAPI 的 TestClient 打真实链路——登录、建题查重、下载模板再传回去导入、组卷存档、三个导出；
`test_exam.py` 覆盖正式考试全流程，其中 `test_answers_never_reach_the_student`
逐字检查学生响应里没有任何答案，**改考试相关代码后一定要看这条还过不过**。
测试跑在临时目录的独立 SQLite 上，不会碰 `data/app.db` 里的真实题库。

**加新知识范围**：管理员在「账号」以外走 `POST /api/dicts`（或直接改 `dict_items` 表）加一条，前端下拉框和导入校验立刻认。不用改代码、不用重新部署。

**数据安全**：题目软删除可恢复；上传原件留底；`backup/backup.sh` 加到 crontab 每天备份，保留 30 天：

```bash
0 2 * * * /opt/exam-system/backup/backup.sh
```

**部署升级**：改完代码在服务器上

```bash
git pull && docker compose up -d --build
```

数据库数据在 docker 卷里、上传目录挂在宿主机 `./data/uploads`，容器重建都不丢。前端更新后学生刷新页面即生效。

**配置**：数据库密码、JWT 密钥全部走环境变量，代码里没有任何明文密码。换 `JWT_SECRET` 会让所有人重新登录，属于正常现象。

---

## 七、已知的待办

原 HTML 的功能已经全部补齐，正式考试也做完了。还没做、按需要再加的部分：

- 操作题在线评分（现在导出 Excel 交给老师人工看，评分不回写系统）
- 考试的开始/结束时间自动控制（现在靠老师手动开关）
- 试卷导出 Word（现在有打印/存 PDF 和导出 Excel，导 docx 要后端加 python-docx）
- 操作日志（谁改了哪道题），现在只记了导入日志
- HTTPS，内网部署可以先不上，对外访问建议在 Nginx 上挂证书

**关于考试的防作弊边界**：口令链接够随机、答案不下发、同一学号只能交一次，
这些挡得住顺手翻源码和重复提交，但挡不住学生互相看屏幕、换个学号再考。
真要严格，还得配合机房环境和监考。
