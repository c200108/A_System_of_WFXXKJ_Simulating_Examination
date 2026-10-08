# 教师端安卓 APP（5.x）

老师手机上用的 APP，安卓 10 及以上。登录页是原生的（服务器地址 + 账号 + 密码），
登进去之后显示的就是服务器上的教师端网页，**功能和电脑上的网页版完全一致**，
网页以后加了功能 APP 不用重新发版。为什么这么做、APP 和服务器怎么通讯，
见 [docs/更新日志/5.0.0.md](../docs/更新日志/5.0.0.md)。

> APP 要连的服务器必须是 **5.0.0 及以上**：手机布局、导出文件、复制链接、自动续期登录
> 都在这一版的服务器里。旧服务器也能登录，但页面是电脑布局、导出存不下来。

## 目录

```
android/
├─ app/src/main/
│  ├─ AndroidManifest.xml      只要「联网」「查看网络状态」两个权限
│  ├─ java/cn/wfxxkj/teacher/
│  │  ├─ LoginActivity.java    原生登录页：先认服务器、再登录
│  │  ├─ MainActivity.java     WebView 主界面：进度条、断网提示、出错页、选文件、返回键
│  │  ├─ SessionKeeper.java    保持登录：前台心跳、令牌续期、过期自动重登、断网重连
│  │  ├─ AppBridge.java        页面里的 window.WfxxApp（网页那一侧是 frontend/src/appBridge.js）
│  │  ├─ FileSaver.java        导出的文件存进「下载/教学平台」
│  │  ├─ Api.java              三个请求：认服务器、登录、心跳
│  │  ├─ Prefs.java            本机保存的地址、账号、令牌
│  │  ├─ CredentialStore.java  密码用系统密钥库加密保存
│  │  └─ Ui.java               全面屏和系统栏留白
│  └─ res/                     界面、图标（全是矢量图，没有 png）
├─ build.gradle / settings.gradle / gradlew(.bat)
└─ keystore.properties         正式签名（自己建，不进 Git）
```

不依赖任何第三方库（没有 AppCompat、没有 OkHttp），安装包不到 100 KB。

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

## 版本号

跟系统的产品线走：5.x = 教师端 APP（含教师端网页的手机适配）。改了 APP 就在
`app/build.gradle` 里同时加 `versionCode` 和 `versionName`，并在
`backend/app/changelog_seed.py` 和 `docs/更新日志/` 里记一笔。

## 装机检查清单

APP 外壳改动后，在真机上过一遍：

- [ ] 地址填错（少端口、填成百度）→ 提示「不是教学平台的服务器」；密码错 → 提示「用户名或密码不正确」
- [ ] 登录后底部五个标签都能进；「我的」里能看到 APP 版本、退出登录回到原生登录页
- [ ] 题库「导出 Excel」、成绩「导出」→ 底部提示已保存，点「打开」能用 WPS 打开
- [ ] 批量导入选 Excel 文件、题目配图选照片 → 能选到并上传
- [ ] 考试「复制」链接 → 粘贴到微信是完整链接
- [ ] 成绩分析「打印」→ 弹出系统打印，能另存为 PDF
- [ ] 切深色模式 → 状态栏和底部手势条跟着变深
- [ ] 开飞行模式 → 顶部黄条「连接已断开」；关掉飞行模式 → 黄条自动消失
- [ ] 后台放过夜（或服务器上把 JWT_EXPIRE_MINUTES 临时改成 5）→ 再打开不用重新登录
- [ ] 在 APP 里改自己的密码 → 退到后台再回来，仍保持登录
- [ ] 返回键：页面内后退；到底了「再按一次退出」
