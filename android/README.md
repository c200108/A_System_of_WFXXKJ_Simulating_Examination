# 教师端安卓 APP（5.x）

老师手机上用的原生 APP，安卓 10 及以上。登录时填服务器地址、账号、密码；
界面全部是原生画的（不打开网页），功能和网页版教师端一一对应，业务数据走同一套 `/api`。
手机竖屏底部标签栏、单列卡片；平板和横屏（≥600dp）左侧导航栏、列表多列、表单并排。支持深色模式。
APP 和服务器怎么通讯，见 [docs/更新日志/5.0.0.md](../docs/更新日志/5.0.0.md)。

> APP 要连的服务器最好是 **5.0.0 及以上**（有认服务器和心跳续期两个接口）。
> 旧服务器也能登录使用，只是没有自动续期。

## 目录（Gradle 多模块）

```
android/
├─ app/            外壳：登录页 LoginActivity、主界面 MainActivity（导航栏/顶栏/页面栈）、
│                  Features.java（五个底部标签怎么拼）
├─ core/           公共库：net（Http/Json）、session（登录、保持登录、密码加密）、
│                  nav（Screen 页面基类、HubScreen 顶部页签）、ui（V 控件构建器、Form 表单、
│                  ItemList 列表、Sheet 弹层、Charts 图表…）、io（导出文件、打印、图片）。
│                  所有资源（颜色、主题、Material 图标）都在这里
├─ feature-paper/    组卷：卷面结构、抽题预览、试卷预览/自测、导出、打印、组卷历史
├─ feature-bank/     题库：题库管理、批量导入、仿真操作题
├─ feature-exam/     考试：发布、学生链接/二维码、提交记录、人工阅卷、成绩分析、样卷
├─ feature-typing/   打字：打字学情（成绩与分析）、练习文本
├─ feature-student/  学生：学生账号、班级
├─ feature-me/       我的：我的账号、账号管理、需求反馈、更新日志、设置、关于
├─ build.gradle / settings.gradle / gradlew(.bat)
└─ keystore.properties   正式签名（自己建，不进 Git）
```

功能模块之间互不依赖，只依赖 core；功能模块里不放资源，图标颜色统一用 `cn.wfxxkj.teacher.core.R`。
加一个模块：新建 `feature-xxx`，在 `settings.gradle`、`app/build.gradle` 里登记，再在 `Features.java` 里挂到某个标签下。

只用安卓系统自带的组件（没有 AndroidX、没有第三方库），安装包约 450 KB。

仿真操作题里 Windows 操作、WPS 文字两类的环境布置和标准答案录制要在模拟桌面上拖拽操作，
手机上做不了，APP 里提示到电脑网页端录制；其余管理操作 APP 里都能做。
## 打包

### 用 Android Studio（推荐）

1. 装 [Android Studio](https://developer.android.google.cn/studio)（自带 JDK 和 SDK）；
2. 「Open」选这个 `android` 文件夹，等它同步完（第一次要下 Gradle 和 SDK，国内已配好镜像）；
3. 菜单 **Build → Generate Signed App Bundle / APK → APK**，选 release；
4. 打好的包在 `app/build/outputs/apk/release/app-release.apk`。

### 命令行

装好 JDK 17 和 Android SDK（`ANDROID_HOME` 指向 SDK 目录）后：

```bat
cd android
gradlew.bat assembleRelease
```

## 签名

**同一个 APP 以后每一版都必须用同一把钥匙签名**，换了钥匙老师手机上就装不上新版，
只能先卸载旧版（卸载会清掉保存的登录）。

第一次生成钥匙（只做一次，生成的文件和密码**务必备份**）：

```bat
keytool -genkeypair -v -keystore wfxx-teacher.jks -alias wfxx -keyalg RSA -keysize 2048 -validity 36500
```

在 `android/` 下新建 `keystore.properties`（已在 .gitignore 里，不会提交）：

```properties
storeFile=wfxx-teacher.jks
storePassword=你设的密码
keyAlias=wfxx
keyPassword=你设的密码
```

没有这个文件时 release 包用调试签名，能装能用，只是以后换成正式签名时要先卸载。

## 发给老师

把 APK 发到老师手机上（微信、QQ、U 盘都行）点开安装。第一次装手机会提示「允许安装未知来源应用」，
按提示允许即可。登录页填：

- **服务器地址**：老师在电脑浏览器里打开教师端用的那个地址，只填到端口，例如 `192.168.1.10:8080`、
  `exam.xxx.cn`。是 https 的要写上 `https://`；
- **账号密码**：和网页版教师端一样。

## 检查更新与发版

「我的 → 检查更新」去**联网版公开仓库**（`c200108/A_System_of_WFXXKJ_Simulating_Examination`）的 Release 列表里
找 tag 以 `teacher-v` 开头的最新正式版，下载 `.apk` 后交给系统安装器（`AppUpdate.java`、`ApkProvider.java`）。
两次检查至少隔 60 秒；整次查询 5 秒封顶，拿不到就提示「无法获取更新」。

发一版：

1. `app/build.gradle` 里 `versionCode`、`versionName` 都加一，`backend/app/changelog_seed.py` 和 `docs/更新日志/` 记一笔；
2. 用**正式签名**打包（`keystore.properties` 在就自动用它）：`gradlew.bat assembleRelease`；
3. 发 Release（tag 必须是 `teacher-v<版本>`，**不要标成 Latest**，Latest 留给学生端 exe）：

   ```bat
   gh release create teacher-v5.1.0 app\build\outputs\apk\release\app-release.apk#教师端APP-5.1.0.apk ^
      --title "教师端 APP 5.1.0" --notes-file 说明.md --latest=false
   ```

   附件名会显示成 `app-release.apk`，想改名先把文件复制成英文名（如 `wfxx-teacher-5.1.0.apk`）再传 ——
   GitHub 会把附件名里的中文换掉。

学生端 exe 只认 `v<数字>` 的 tag，APP 只认 `teacher-v…`，两边发在同一个仓库里不会互相干扰。

## 版本号

跟系统的产品线走：5.x = 教师端 APP。改了 APP 就在
`app/build.gradle` 里同时加 `versionCode` 和 `versionName`，并在
`backend/app/changelog_seed.py` 和 `docs/更新日志/` 里记一笔。

## 装机检查清单

APP 改动后，在真机上过一遍（手机竖屏、横屏、平板各看一次）：

- [ ] 地址填错（少端口、填成百度）→ 提示「不是教学平台的服务器」；密码错 → 提示「用户名或密码不正确」
- [ ] 登录后底部五个标签都能进，每个页签都有数据；「我的 → 关于」能看到 APP 版本，退出登录回到登录页
- [ ] 题库「导出 Excel」、成绩「导出」→ 底部提示已保存，点「打开」能用 WPS 打开
- [ ] 批量导入选 Excel 文件、题目配图选照片 → 能选到并上传
- [ ] 考试「复制」链接 → 粘贴到微信是完整链接
- [ ] 成绩分析「打印」→ 弹出系统打印，能另存为 PDF
- [ ] 切深色模式 → 状态栏和底部手势条跟着变深
- [ ] 开飞行模式 → 顶部黄条「连接已断开」；关掉飞行模式 → 黄条自动消失
- [ ] 后台放过夜（或服务器上把 JWT_EXPIRE_MINUTES 临时改成 5）→ 再打开不用重新登录
- [ ] 在 APP 里改自己的密码 → 退到后台再回来，仍保持登录
- [ ] 返回键：逐层返回；到底了「再按一次退出」
- [ ] 转屏、分屏改大小：布局按新宽度重排，正在填的表单不丢
- [ ] 需求反馈里的图片能显示（截图工具里没能验证）
