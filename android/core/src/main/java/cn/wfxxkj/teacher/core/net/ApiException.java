package cn.wfxxkj.teacher.core.net;

/**
 * 请求失败。{@link #code} 是 HTTP 状态码，连不上服务器时为 0；
 * {@link #getMessage()} 是能直接给老师看的一句中文。
 */
public class ApiException extends Exception {
    public final int code;
    /** 后端原始的 detail（可能是字符串、数组或对象），需要细看时用 */
    public final Object detail;

    public ApiException(int code, String message) {
        this(code, message, null);
    }

    public ApiException(int code, String message, Object detail) {
        super(message);
        this.code = code;
        this.detail = detail;
    }

    /** 网络不通、服务器没开（不是业务上的拒绝） */
    public boolean isNetwork() {
        return code == 0;
    }
}
