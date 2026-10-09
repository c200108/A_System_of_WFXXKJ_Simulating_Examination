package cn.wfxxkj.teacher.exam;

import java.nio.charset.StandardCharsets;

/**
 * 最小的二维码编码器（字节模式、纠错等级 M、版本 1–10），给学生链接生成二维码用。
 * 不引第三方库；算法按 ISO/IEC 18004 标准实现（思路同 Nayuki 的开源实现）。
 * 版本 10 能装 213 个字节，考试链接一般 40～80 个字符，足够。
 */
final class QrCode {
    /** 每块的纠错码字数（纠错等级 M，下标 = 版本号） */
    private static final int[] ECC_PER_BLOCK = {-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26};
    /** 纠错块数（纠错等级 M） */
    private static final int[] NUM_BLOCKS = {-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5};
    private static final int MAX_VERSION = 10;
    /** 纠错等级 M 在格式信息里的两位 */
    private static final int ECL_FORMAT_BITS = 0;

    final int size;
    private final boolean[][] modules;
    private final boolean[][] isFunction;

    /** 编码一段文字。太长（超过版本 10 的容量）抛 IllegalArgumentException */
    static QrCode encode(String text) {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        int version = 1;
        for (; version <= MAX_VERSION; version++) {
            int cap = numDataCodewords(version) * 8;
            int used = 4 + (version <= 9 ? 8 : 16) + data.length * 8;
            if (used <= cap) break;
        }
        if (version > MAX_VERSION) throw new IllegalArgumentException("链接太长，生成不了二维码");
        return new QrCode(version, data);
    }

    /** 第 y 行第 x 列是不是黑块 */
    boolean get(int x, int y) {
        return x >= 0 && x < size && y >= 0 && y < size && modules[y][x];
    }

    private QrCode(int version, byte[] data) {
        size = version * 4 + 17;
        modules = new boolean[size][size];
        isFunction = new boolean[size][size];

        // 1. 数据位：模式 0100 + 长度 + 内容 + 结束符 + 补齐
        int capBits = numDataCodewords(version) * 8;
        BitBuf bb = new BitBuf(capBits);
        bb.append(0x4, 4);
        bb.append(data.length, version <= 9 ? 8 : 16);
        for (byte b : data) bb.append(b & 0xFF, 8);
        bb.append(0, Math.min(4, capBits - bb.len));
        bb.append(0, (8 - bb.len % 8) % 8);
        for (int pad = 0xEC; bb.len < capBits; pad ^= 0xEC ^ 0x11) bb.append(pad, 8);
        byte[] dataCodewords = new byte[capBits / 8];
        for (int i = 0; i < bb.len; i++) {
            if (bb.bits[i]) dataCodewords[i >>> 3] |= (byte) (1 << (7 - (i & 7)));
        }

        // 2. 纠错码并交织
        byte[] all = addEccAndInterleave(version, dataCodewords);

        // 3. 画功能图形、放数据、选掩码
        drawFunctionPatterns(version);
        drawCodewords(all);
        int bestMask = 0;
        long minPenalty = Long.MAX_VALUE;
        for (int m = 0; m < 8; m++) {
            applyMask(m);
            drawFormatBits(m);
            long p = penalty();
            if (p < minPenalty) {
                minPenalty = p;
                bestMask = m;
            }
            applyMask(m); // 掩码是异或，再做一次就还原
        }
        applyMask(bestMask);
        drawFormatBits(bestMask);
    }

    // ---------- 容量 ----------

    private static int numRawDataModules(int ver) {
        int result = (16 * ver + 128) * ver + 64;
        if (ver >= 2) {
            int numAlign = ver / 7 + 2;
            result -= (25 * numAlign - 10) * numAlign - 55;
            if (ver >= 7) result -= 36;
        }
        return result;
    }

    private static int numDataCodewords(int ver) {
        return numRawDataModules(ver) / 8 - ECC_PER_BLOCK[ver] * NUM_BLOCKS[ver];
    }

    // ---------- 纠错 ----------

    private static byte[] addEccAndInterleave(int ver, byte[] data) {
        int numBlocks = NUM_BLOCKS[ver];
        int blockEccLen = ECC_PER_BLOCK[ver];
        int rawCodewords = numRawDataModules(ver) / 8;
        int numShortBlocks = numBlocks - rawCodewords % numBlocks;
        int shortBlockLen = rawCodewords / numBlocks;

        byte[][] blocks = new byte[numBlocks][];
        byte[] divisor = rsDivisor(blockEccLen);
        for (int i = 0, k = 0; i < numBlocks; i++) {
            int datLen = shortBlockLen - blockEccLen + (i < numShortBlocks ? 0 : 1);
            byte[] dat = new byte[datLen];
            System.arraycopy(data, k, dat, 0, datLen);
            k += datLen;
            byte[] ecc = rsRemainder(dat, divisor);
            byte[] block = new byte[shortBlockLen + 1];
            // 短块在数据末尾空出一位（交织时跳过）
            int pos = 0;
            for (byte b : dat) block[pos++] = b;
            if (i < numShortBlocks) pos++;
            for (byte b : ecc) block[pos++] = b;
            blocks[i] = block;
        }
        byte[] result = new byte[rawCodewords];
        int r = 0;
        for (int i = 0; i < blocks[0].length; i++) {
            for (int j = 0; j < blocks.length; j++) {
                if (i != shortBlockLen - blockEccLen || j >= numShortBlocks) result[r++] = blocks[j][i];
            }
        }
        return result;
    }

    private static byte[] rsDivisor(int degree) {
        byte[] result = new byte[degree];
        result[degree - 1] = 1;
        int root = 1;
        for (int i = 0; i < degree; i++) {
            for (int j = 0; j < result.length; j++) {
                result[j] = (byte) mul(result[j] & 0xFF, root);
                if (j + 1 < result.length) result[j] ^= result[j + 1];
            }
            root = mul(root, 0x02);
        }
        return result;
    }

    private static byte[] rsRemainder(byte[] data, byte[] divisor) {
        byte[] result = new byte[divisor.length];
        for (byte b : data) {
            int factor = (b ^ result[0]) & 0xFF;
            System.arraycopy(result, 1, result, 0, result.length - 1);
            result[result.length - 1] = 0;
            for (int i = 0; i < result.length; i++) result[i] ^= (byte) mul(divisor[i] & 0xFF, factor);
        }
        return result;
    }

    private static int mul(int x, int y) {
        int z = 0;
        for (int i = 7; i >= 0; i--) {
            z = (z << 1) ^ ((z >>> 7) * 0x11D);
            z ^= ((y >>> i) & 1) * x;
        }
        return z & 0xFF;
    }

    // ---------- 画图形 ----------

    private void set(int x, int y, boolean dark) {
        modules[y][x] = dark;
        isFunction[y][x] = true;
    }

    private void drawFunctionPatterns(int ver) {
        for (int i = 0; i < size; i++) {
            set(6, i, i % 2 == 0);
            set(i, 6, i % 2 == 0);
        }
        drawFinder(3, 3);
        drawFinder(size - 4, 3);
        drawFinder(3, size - 4);
        int[] pos = alignmentPositions(ver);
        int n = pos.length;
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                if (!(i == 0 && j == 0 || i == 0 && j == n - 1 || i == n - 1 && j == 0)) drawAlignment(pos[i], pos[j]);
            }
        }
        drawFormatBits(0); // 先占位，选好掩码后重画
        if (ver >= 7) {
            int rem = ver;
            for (int i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1F25);
            long bits = ((long) ver << 12) | rem;
            for (int i = 0; i < 18; i++) {
                boolean bit = ((bits >>> i) & 1) != 0;
                int a = size - 11 + i % 3, b = i / 3;
                set(a, b, bit);
                set(b, a, bit);
            }
        }
    }

    private void drawFinder(int x, int y) {
        for (int dy = -4; dy <= 4; dy++) {
            for (int dx = -4; dx <= 4; dx++) {
                int dist = Math.max(Math.abs(dx), Math.abs(dy));
                int xx = x + dx, yy = y + dy;
                if (xx >= 0 && xx < size && yy >= 0 && yy < size) set(xx, yy, dist != 2 && dist != 4);
            }
        }
    }

    private void drawAlignment(int x, int y) {
        for (int dy = -2; dy <= 2; dy++) {
            for (int dx = -2; dx <= 2; dx++) set(x + dx, y + dy, Math.max(Math.abs(dx), Math.abs(dy)) != 1);
        }
    }

    private int[] alignmentPositions(int ver) {
        if (ver == 1) return new int[0];
        int numAlign = ver / 7 + 2;
        int step = (ver * 4 + numAlign * 2 + 1) / (numAlign * 2 - 2) * 2;
        int[] result = new int[numAlign];
        result[0] = 6;
        for (int i = numAlign - 1, p = size - 7; i >= 1; i--, p -= step) result[i] = p;
        return result;
    }

    private void drawFormatBits(int mask) {
        int data = ECL_FORMAT_BITS << 3 | mask;
        int rem = data;
        for (int i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
        int bits = (data << 10 | rem) ^ 0x5412;
        for (int i = 0; i <= 5; i++) set(8, i, bit(bits, i));
        set(8, 7, bit(bits, 6));
        set(8, 8, bit(bits, 7));
        set(7, 8, bit(bits, 8));
        for (int i = 9; i < 15; i++) set(14 - i, 8, bit(bits, i));
        for (int i = 0; i < 8; i++) set(size - 1 - i, 8, bit(bits, i));
        for (int i = 8; i < 15; i++) set(8, size - 15 + i, bit(bits, i));
        set(8, size - 8, true);
    }

    private static boolean bit(int x, int i) {
        return ((x >>> i) & 1) != 0;
    }

    private void drawCodewords(byte[] data) {
        int i = 0;
        for (int right = size - 1; right >= 1; right -= 2) {
            if (right == 6) right = 5;
            for (int vert = 0; vert < size; vert++) {
                for (int j = 0; j < 2; j++) {
                    int x = right - j;
                    boolean upward = ((right + 1) & 2) == 0;
                    int y = upward ? size - 1 - vert : vert;
                    if (!isFunction[y][x] && i < data.length * 8) {
                        modules[y][x] = bit(data[i >>> 3], 7 - (i & 7));
                        i++;
                    }
                }
            }
        }
    }

    private void applyMask(int mask) {
        for (int y = 0; y < size; y++) {
            for (int x = 0; x < size; x++) {
                boolean invert;
                switch (mask) {
                    case 0: invert = (x + y) % 2 == 0; break;
                    case 1: invert = y % 2 == 0; break;
                    case 2: invert = x % 3 == 0; break;
                    case 3: invert = (x + y) % 3 == 0; break;
                    case 4: invert = (x / 3 + y / 2) % 2 == 0; break;
                    case 5: invert = x * y % 2 + x * y % 3 == 0; break;
                    case 6: invert = (x * y % 2 + x * y % 3) % 2 == 0; break;
                    default: invert = ((x + y) % 2 + x * y % 3) % 2 == 0; break;
                }
                if (!isFunction[y][x] && invert) modules[y][x] = !modules[y][x];
            }
        }
    }

    /** 掩码评分（标准的四条规则，简化了第三条的判断），越小越好扫 */
    private long penalty() {
        long result = 0;
        // 规则 1：同色连续 5 个以上
        for (int y = 0; y < size; y++) {
            int runX = 1, runY = 1;
            for (int x = 1; x < size; x++) {
                if (modules[y][x] == modules[y][x - 1]) {
                    runX++;
                    if (runX == 5) result += 3;
                    else if (runX > 5) result++;
                } else runX = 1;
                if (modules[x][y] == modules[x - 1][y]) {
                    runY++;
                    if (runY == 5) result += 3;
                    else if (runY > 5) result++;
                } else runY = 1;
            }
        }
        // 规则 2：2×2 同色块
        for (int y = 0; y < size - 1; y++) {
            for (int x = 0; x < size - 1; x++) {
                boolean c = modules[y][x];
                if (c == modules[y][x + 1] && c == modules[y + 1][x] && c == modules[y + 1][x + 1]) result += 3;
            }
        }
        // 规则 3：像定位图形的 1:1:3:1:1 样式
        for (int y = 0; y < size; y++) {
            for (int x = 0; x + 6 < size; x++) {
                if (finderLike(y, x, true)) result += 40;
                if (finderLike(y, x, false)) result += 40;
            }
        }
        // 规则 4：黑白比例
        int dark = 0;
        for (boolean[] row : modules) for (boolean b : row) if (b) dark++;
        int total = size * size;
        int k = (Math.abs(dark * 20 - total * 10) + total - 1) / total - 1;
        result += Math.max(0, k) * 10L;
        return result;
    }

    /** 从 (a, b) 开始横向（horizontal）或纵向的 7 格是不是 黑白黑黑黑白黑，且一侧有 4 格白 */
    private boolean finderLike(int a, int b, boolean horizontal) {
        boolean[] pat = {true, false, true, true, true, false, true};
        for (int i = 0; i < 7; i++) {
            boolean v = horizontal ? modules[a][b + i] : modules[b + i][a];
            if (v != pat[i]) return false;
        }
        boolean before = true, after = true;
        for (int i = 1; i <= 4; i++) {
            int p1 = b - i, p2 = b + 6 + i;
            if (p1 >= 0 && (horizontal ? modules[a][p1] : modules[p1][a])) before = false;
            if (p2 < size && (horizontal ? modules[a][p2] : modules[p2][a])) after = false;
        }
        return before || after;
    }

    /** 往后追加位的小缓冲 */
    private static final class BitBuf {
        final boolean[] bits;
        int len;

        BitBuf(int cap) {
            bits = new boolean[cap];
        }

        void append(int val, int n) {
            for (int i = n - 1; i >= 0; i--) {
                if (len < bits.length) bits[len] = ((val >>> i) & 1) != 0;
                len++;
            }
        }
    }
}
