# 网页通过 window.WfxxApp 调这些方法，名字不能被混淆掉
-keepclassmembers class cn.wfxxkj.teacher.AppBridge {
    @android.webkit.JavascriptInterface <methods>;
}
-keepattributes JavascriptInterface
