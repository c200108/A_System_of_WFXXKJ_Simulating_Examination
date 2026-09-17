<script setup>
/**
 * AI 工具题：一个通用的 AI 对话界面。
 *
 * 题干本身就是要求（「请使用给定的 AI 工具，生成一份……」），学生要做的是
 * **把要求清楚地提给工具**。所以判分点只有两个，都在服务端算（services/sim.py）：
 *   ① 提交过提问   ② 提问内容覆盖题目要求
 * 老师不用做标准答案，也不用出检查点。
 *
 * ## 回复是本地模板拼的，不是真的大模型
 *
 * 界面上写明了这一点，不能让学生以为这是真 AI。理由有三条：
 *   · 考试环境不该往外发网络请求，一个机房五十台机器同时问，出口先挂；
 *   · 真模型的回复不可控，考试里出现什么内容没人兜得住；
 *   · 这类题考的是"会不会把需求说清楚"，不是"模型答得好不好"——
 *     模型答得好不好也不该由学生负责。
 *
 * 要接真模型的话，把 reply() 换成调后端接口即可，判分那边一个字都不用动。
 */
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  env: { type: Object, required: true },
  modelValue: { type: Object, default: null },
  readonly: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'log'])

const messages = ref([])
const draft = ref('')
const thinking = ref(false)
const box = ref(null)

const tool = computed(() => props.env?.tool || 'AI 助手')

function boot() {
  const src = props.modelValue && Array.isArray(props.modelValue.messages) ? props.modelValue : null
  messages.value = src ? JSON.parse(JSON.stringify(src.messages)) : []
  draft.value = ''
}
boot()
watch(() => props.env, boot)

function push(action) {
  emit('update:modelValue', { messages: JSON.parse(JSON.stringify(messages.value)) })
  if (action) emit('log', { at: Date.now(), ...action })
}

async function scrollDown() {
  await nextTick()
  if (box.value) box.value.scrollTop = box.value.scrollHeight
}

/** 按提问里的关键词拼一段像模像样的回复。纯本地，不联网。 */
function reply(ask) {
  const t = String(ask || '')
  const head = `好的，我来帮你完成。以下是根据你的要求生成的内容：`
  const tail = `\n\n以上内容由仿真环境按模板生成，仅用于演示 AI 工具的使用流程。`

  if (/代码|程序|python|编程|函数/i.test(t)) {
    return `${head}\n\n# 参考代码\nfor i in range(1, 11):\n    print(i)\n\n说明：上面的程序按你的要求输出结果，可按需修改变量和范围。${tail}`
  }
  if (/表格|统计|清单|列出/.test(t)) {
    return `${head}\n\n序号 | 项目 | 说明\n1 | 第一项 | 按你的要求整理\n2 | 第二项 | 可继续补充\n3 | 第三项 | 可继续补充${tail}`
  }
  if (/图|海报|封面|设计/.test(t)) {
    return `${head}\n\n已按你的描述给出设计思路：主体元素、配色、版式各一条，可据此再细化提示词。${tail}`
  }
  if (/翻译/.test(t)) {
    return `${head}\n\n（译文）这里是按你提供的原文生成的译文，语序与用词已按中文习惯调整。${tail}`
  }
  const n = t.replace(/\s+/g, '').length
  return `${head}\n\n围绕你提出的要求，可以从三个方面展开：一是背景与意义，二是具体内容与做法，三是总结与延伸。` +
    `你的要求共 ${n} 个字，其中的关键信息我已经全部采纳。${tail}`
}

function send() {
  const text = draft.value.trim()
  if (!text || props.readonly || thinking.value) return
  messages.value.push({ role: 'user', text, at: Date.now() })
  draft.value = ''
  push({ op: 'ask', len: text.length })
  scrollDown()

  // 停顿一下再出回复，像真的在生成；时间很短，不耽误考试
  thinking.value = true
  setTimeout(() => {
    messages.value.push({ role: 'ai', text: reply(text), at: Date.now() })
    thinking.value = false
    push({ op: 'reply' })
    scrollDown()
  }, 420)
}

function onKey(e) {
  // 回车发送、Shift+回车换行，和常见的聊天工具一致
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

const asked = computed(() => messages.value.filter(m => m.role === 'user').length)
</script>

<template>
  <div class="ai">
    <div class="head">
      <span class="logo">✦</span>
      <b>{{ tool }}</b>
      <span class="grow" />
      <span class="note">仿真环境 · 回复由本地模板生成，不联网</span>
    </div>

    <div ref="box" class="chat">
      <div class="msg ai-msg">
        <span class="avatar">✦</span>
        <div class="bubble">{{ env.greeting || '你好，把题目要求发给我，我来帮你完成。' }}</div>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role === 'user' ? 'me' : 'ai-msg'">
        <span v-if="m.role !== 'user'" class="avatar">✦</span>
        <div class="bubble">{{ m.text }}</div>
        <span v-if="m.role === 'user'" class="avatar me-a">我</span>
      </div>

      <div v-if="thinking" class="msg ai-msg">
        <span class="avatar">✦</span>
        <div class="bubble dots"><i /><i /><i /></div>
      </div>
    </div>

    <div class="composer">
      <textarea
        v-model="draft"
        :readonly="readonly"
        rows="3"
        placeholder="把题目要求完整地描述给 AI 工具，然后按「发送」（回车发送，Shift+回车换行）"
        @keydown="onKey"
      />
      <button class="send" :disabled="readonly || !draft.trim() || thinking" @click="send">发送</button>
    </div>

    <p class="foot">
      <template v-if="asked">已经向 {{ tool }} 提交了 {{ asked }} 次提问。</template>
      <template v-else>还没有提交提问 —— 把题目里的要求写清楚发过去。</template>
    </p>
  </div>
</template>

<style scoped>
.ai {
  display: flex; flex-direction: column;
  border: 1px solid #d9dee8; border-radius: 8px; overflow: hidden; background: #fff;
  font: 13px/1.6 "Microsoft YaHei", sans-serif;
}
.head {
  display: flex; align-items: center; gap: 8px; padding: 8px 14px;
  background: linear-gradient(90deg, #eef3ff, #f7f9ff); border-bottom: 1px solid #e6eaf2;
}
.logo {
  width: 22px; height: 22px; border-radius: 6px; display: grid; place-items: center;
  background: linear-gradient(135deg, #5b8def, #8b5bef); color: #fff; font-size: 13px;
}
.grow { flex: 1; }
.note { font-size: 11.5px; color: #98a1b3; }

.chat { height: 300px; overflow: auto; padding: 14px; background: #f7f8fb; display: flex; flex-direction: column; gap: 12px; }
.msg { display: flex; gap: 8px; align-items: flex-start; }
.msg.me { flex-direction: row; justify-content: flex-end; }
.avatar {
  width: 26px; height: 26px; flex: none; border-radius: 50%; display: grid; place-items: center;
  background: linear-gradient(135deg, #5b8def, #8b5bef); color: #fff; font-size: 12px;
}
.avatar.me-a { background: #5cb85c; }
.bubble {
  max-width: 78%; padding: 8px 12px; border-radius: 10px; background: #fff;
  border: 1px solid #e6eaf2; white-space: pre-wrap; word-break: break-word;
}
.msg.me .bubble { background: #d9ecff; border-color: #b9d8f7; }
.dots { display: flex; gap: 4px; align-items: center; height: 20px; }
.dots i { width: 6px; height: 6px; border-radius: 50%; background: #b9c2d0; animation: blink 1.1s infinite; }
.dots i:nth-child(2) { animation-delay: 0.2s; }
.dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%, 60%, 100% { opacity: 0.3 } 30% { opacity: 1 } }

.composer { display: flex; gap: 8px; padding: 10px; border-top: 1px solid #e6eaf2; }
.composer textarea {
  flex: 1; border: 1px solid #d9dee8; border-radius: 6px; padding: 8px 10px;
  font: inherit; resize: vertical; outline: none;
}
.composer textarea:focus { border-color: #5b8def; }
.send {
  width: 76px; border: none; border-radius: 6px; cursor: pointer; font: inherit;
  color: #fff; background: linear-gradient(135deg, #5b8def, #4a7bdc);
}
.send:disabled { background: #c9d2e0; cursor: default; }
.foot { margin: 0; padding: 0 12px 10px; font-size: 12px; color: #8a919c; }
</style>
