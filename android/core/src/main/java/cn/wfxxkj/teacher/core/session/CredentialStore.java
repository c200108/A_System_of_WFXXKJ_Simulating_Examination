package cn.wfxxkj.teacher.core.session;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * 用系统密钥库（Android Keystore）加密保存的密码。
 *
 * 密钥生成在系统的安全区里、导不出来，别的应用读不到；就算有人把这个应用的数据目录
 * 整个拷走，拿到的也只是一串密文。卸载应用时密钥跟着删除。
 */
public final class CredentialStore {
    private static final String ALIAS = "wfxx_teacher_cred";
    private static final String STORE = "AndroidKeyStore";
    private static final String TRANSFORM = "AES/GCM/NoPadding";

    private CredentialStore() {}

    private static SecretKey key() throws Exception {
        KeyStore ks = KeyStore.getInstance(STORE);
        ks.load(null);
        KeyStore.Entry entry = ks.getEntry(ALIAS, null);
        if (entry instanceof KeyStore.SecretKeyEntry) {
            return ((KeyStore.SecretKeyEntry) entry).getSecretKey();
        }
        KeyGenerator gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, STORE);
        gen.init(new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build());
        return gen.generateKey();
    }

    /** 加密失败（极少数改过系统的手机）返回 null，那就不存密码，只是不能自动重新登录 */
    public static String encrypt(String plain) {
        if (plain == null) return null;
        try {
            Cipher c = Cipher.getInstance(TRANSFORM);
            c.init(Cipher.ENCRYPT_MODE, key());
            byte[] iv = c.getIV();
            byte[] body = c.doFinal(plain.getBytes(StandardCharsets.UTF_8));
            byte[] all = new byte[1 + iv.length + body.length];
            all[0] = (byte) iv.length;
            System.arraycopy(iv, 0, all, 1, iv.length);
            System.arraycopy(body, 0, all, 1 + iv.length, body.length);
            return Base64.encodeToString(all, Base64.NO_WRAP);
        } catch (Exception e) {
            return null;
        }
    }

    public static String decrypt(String encoded) {
        try {
            byte[] all = Base64.decode(encoded, Base64.NO_WRAP);
            int ivLen = all[0];
            byte[] iv = new byte[ivLen];
            System.arraycopy(all, 1, iv, 0, ivLen);
            Cipher c = Cipher.getInstance(TRANSFORM);
            c.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
            byte[] plain = c.doFinal(all, 1 + ivLen, all.length - 1 - ivLen);
            return new String(plain, StandardCharsets.UTF_8);
        } catch (Exception e) {
            return null;
        }
    }
}
