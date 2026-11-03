# API 数据接入规范（2.16.0 起）

老师在教师端「API」板块新建一个 API，得到**接收编号**（地址里那串）和**写入密钥**。
老师自己做的答题网页、自评互评表、问卷、小程序把数据送到下面的地址，平台存下来，
在「数据表单」「数据大图」里看；学号对得上平台名单的学生，数据还会汇总进他的「学情」。

各老师的 API 和数据互不相通，管理员可看全部。

## 1. 地址与鉴权

```
POST  https://服务器/api/hook/{接收编号}
```

写入密钥四种带法都认（HTML 表单、sendBeacon 设不了请求头，所以后两种也收）：

| 带法 | 例子 | 适合 |
|---|---|---|
| `Authorization: Bearer 密钥` | 请求头 | 服务器端程序（推荐） |
| `X-Api-Key: 密钥` | 请求头 | 网页 fetch |
| `?token=密钥` | 地址参数 | 只能拼链接的工具 |
| `_token` 字段 | JSON 或表单里 | HTML 表单、sendBeacon |

写入密钥会写进学生网页，等于半公开：它**只能往这个 API 里写**，看不到任何数据。
泄露了在「接入说明」里重新生成。防乱刷靠：限频（同一设备每分钟 30 条、认不出设备时同一 IP 每分钟 600 条、
同一 API 每小时 5000 条）、大小上限、接收时间段、暂停开关、来源网站白名单、每个 API 5 万条上限。

## 2. 能收的格式

| Content-Type | 说明 |
|---|---|
| `application/json` | 一个对象 = 一条；一个数组 = 批量（最多 500 条）；`{"records": [...]}` 也算批量 |
| `text/plain`（内容是 JSON） | `navigator.sendBeacon`，关页面时也能发出去，不触发跨域预检 |
| `application/x-www-form-urlencoded` / `multipart/form-data` | 纯 HTML 表单直接提交；带 `_redirect`（http/https 地址）就提交完跳回去，地址后加 `?wfxx=ok` |
| `GET` + 地址参数 | 默认关闭，老师在设置里打开「允许 GET 提交」 |

大小：单条 256 KB，一次请求 2 MB。

## 3. 推荐的数据格式（标准信封）

**每一项都可以不填**，填了的平台会拆出来做筛选和统计：

```json
{
  "client_id": "0b6f2c1e-…",
  "type": "answer",
  "activity": {"id": "L3-T1", "name": "第3课 任务1"},
  "student": {"no": "20250101", "name": "张三", "class": "七年级1班"},
  "target":  {"no": "20250102", "name": "李四"},
  "score": 8, "max_score": 10,
  "answers": [
    {"q": "1", "answer": "B", "correct": true, "score": 2, "max": 2, "time_ms": 5300}
  ],
  "ratings": [
    {"item": "合作交流", "score": 4, "max": 5}
  ],
  "comment": "这次分工很清楚",
  "page": "https://teach.example.com/l3/index.html",
  "data": {"任意": "自定义内容原样保存"},
  "submitted_at": "2026-11-03T09:30:00+08:00"
}
```

| 字段 | 说明 |
|---|---|
| `client_id` | 这一条的唯一编号（≤64 字）。同一 API 下重复的不再入库，回执里 `duplicate: true` —— 断网重发放心发 |
| `type` | `answer` 答题 / `self_eval` 自评 / `peer_eval` 互评 / `survey` 问卷 / `event` 操作记录，或自定义字符串。不填按 API 的用途算 |
| `activity` | 哪节课、哪个任务。也可以直接写一个字符串 |
| `student` | 学生。学号对上平台名单（或「班级 + 姓名」唯一对上）的，汇总进学情 |
| `target` | 互评的被评人 |
| `score` / `max_score` | 总分 / 满分。不填 `score` 但 `answers` 里每题有分的，自动加总 |
| `answers` | 逐题：`q` 题号、`answer` 作答、`correct` 对错、`score`/`max` 得分满分、`time_ms` 用时。也可以写成 `{"1": "B", "2": "C"}` |
| `ratings` | 评价维度：`item` 维度名、`score`、`max`。也可以写成 `{"合作": 4, "表达": 5}` |
| `comment` | 评语、反思 |
| `page` | 来源网页。不填用浏览器带的 Referer；`?` 和 `#` 后面的会去掉，同一个网页算一个 |
| `data` | 其他任意内容，原样保存，数据表单里自动成列 |
| `submitted_at` | 第三方记的提交时间（ISO 8601，或秒／毫秒时间戳） |

用法举例：

- 自评：`type: "self_eval"`，填 `ratings` 和 `comment`；
- 互评：`type: "peer_eval"`，`student` 是评价人，`target` 是被评人；
- 问卷：`type: "survey"`，题目和选项放 `answers`（不判对错就不填 `correct`）。

### 不按信封来也收

任意 JSON 或表单整条原样存下，再按常见别名去认：

| 认成 | 别名 |
|---|---|
| 学号 | `student_no` `studentNo` `sno` `xh` `student_id` `学号` |
| 姓名 | `name` `student_name` `xm` `姓名` `学生` |
| 班级 | `class` `class_name` `bj` `班级` |
| 得分 / 满分 | `score` `得分` `分数` `成绩` / `max_score` `满分` |
| 评语 | `comment` `remark` `feedback` `评语` `反思` `感想` |
| 活动 | `activity` `task` `lesson` `活动` `任务` |

顶层和 `data` 里面都找。认不出的字段照样显示在数据表单里，老师可以在「设置 → 字段名称」里起中文名、隐藏。

## 4. 回执

成功（新入库 201，重复 200）：

```json
{"ok": true, "id": 1024, "received_at": "2026-11-03T09:30:01+08:00",
 "duplicate": false, "student_matched": true}
```

批量（200）：

```json
{"ok": true, "accepted": 28, "duplicates": 2, "rejected": 0, "received_at": "…",
 "results": [{"ok": true, "id": 1025, "duplicate": false, "student_matched": true}, …]}
```

`results` 和传进来的顺序一一对应；有一条被拒时 `ok` 为 false，其余照常入库。

失败统一格式：`{"ok": false, "code": "TOKEN_INVALID", "message": "写入密钥不对"}`

| HTTP | code | 含义 |
|---|---|---|
| 400 | `BAD_JSON` | 声明是 JSON 但解析不了 |
| 401 | `TOKEN_MISSING` / `TOKEN_INVALID` | 没带密钥 / 密钥不对 |
| 403 | `ORIGIN_DENIED` | 浏览器来源网站不在老师设的白名单里 |
| 404 | `API_NOT_FOUND` | 接收编号不存在或 API 已删除 |
| 405 | `GET_DISABLED` | 没开「允许 GET」 |
| 413 | `PAYLOAD_TOO_LARGE` / `TOO_MANY` | 太大 / 一次超过 500 条 |
| 415 | `UNSUPPORTED_TYPE` | 认不出格式 |
| 422 | `EMPTY` | 内容是空的 |
| 423 | `PAUSED` / `OUT_OF_WINDOW` | 已暂停 / 不在接收时间段 |
| 429 | `RATE_LIMITED` | 太快了，响应头 `Retry-After` 说等几秒 |
| 507 | `QUOTA_FULL` | 这个 API 存满 5 万条 |

## 5. 传出：读取接口

读取密钥默认关闭，老师在「接入说明」里开启。**只能放在服务器端程序里，不要写进网页。**

```
GET /api/hook/{接收编号}/records?after_id=0&limit=100&since=&type=&activity=
Authorization: Bearer 读取密钥
```

返回 `{"ok": true, "records": [...], "next_after_id": 1124}`，按 id 从小到大；`next_after_id` 不为空就带上它再取下一页。
每条记录：`id client_id type activity student target score max_score comment page flag superseded submitted_at received_at payload`。

```
GET /api/hook/{接收编号}/summary?activity=
```

不含任何学生个人信息的汇总：`records people avg_score avg_rate max_score min_score questions(各题正确率) dimensions(各维度自评/互评平均) distribution`。
用读取密钥可以取；老师在设置里打开「学生网页可以用写入密钥读全班汇总」后，写入密钥也能取 —— 适合学生交完在网页上显示「全班平均」。

## 6. 跨域

`/api/hook/` 下的接口对任何网站放行跨域（不带 Cookie，靠密钥），预检请求直接通过；
「只允许哪些网站」由每个 API 的来源网站白名单判。白名单只管浏览器（看 Origin / Referer），服务器端程序不受影响。

## 7. 接入小工具 sdk.js

```html
<script src="https://服务器/api/hook/sdk.js"></script>
<script>
  const api = WFXX.api('接收编号', '写入密钥');
  api.send({ type: 'answer', student: { no: '20250101', name: '张三' }, score: 8 })
     .then(r => console.log(r));      // 回执，见第 4 节
  // 关页面时：api.beacon({...})
  // 全班汇总：api.summary().then(s => …)
</script>
```

自动带 `client_id`、来源网页、提交时间、设备号；断网或服务器暂时不可用时先存在浏览器里，联网后／下次打开页面自动补发（最多存 500 条）。

## 8. 存多久

默认一直保留；每个 API 最多 5 万条，存满拒收并提示老师清理。老师可以在数据表单里删除、清空（进回收站，7 天内可还原），
删除整个 API 也进回收站。
