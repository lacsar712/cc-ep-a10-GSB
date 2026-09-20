<template>
  <div class="page">
    <div>
      <h1 style="margin-bottom: 4px">事件回放</h1>
      <p class="muted" style="margin-top: 0">
        只读演示：从第 1 版起逐版前进，查看每一步之后的状态。回放不写入正式投影。
      </p>
    </div>

    <div class="card" style="margin-bottom: 16px">
      <n-form-item label="选择 Run" :show-feedback="false" style="margin-bottom: 0">
        <n-select
          v-model:value="selectedRun"
          filterable
          :options="runOptions"
          :loading="loadingRuns"
          placeholder="选择一个 Run 开始回放"
          @update:value="onSelectRun"
        />
      </n-form-item>
    </div>

    <template v-if="replay">
      <div class="card" style="margin-bottom: 16px">
        <div style="display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap">
          <div>
            <strong>{{ replay.name }}</strong>
            <span class="muted"> · {{ replay.project }}</span>
          </div>
          <div style="display: flex; gap: 8px; align-items: center">
            <n-button size="small" :disabled="stepIndex === 0" @click="reset">复位</n-button>
            <n-button
              size="small"
              type="primary"
              :disabled="stepIndex >= replay.steps.length - 1"
              @click="stepForward"
            >
              下一版 ▶
            </n-button>
          </div>
        </div>
        <n-progress
          style="margin-top: 12px"
          type="line"
          :percentage="progressPct"
          :indicator-text-color="'#5c6b7a'"
        >
          第 {{ current.version }} 版 / 共 {{ replay.total_versions }} 版
        </n-progress>
      </div>

      <div class="grid-2">
        <div class="card">
          <h3 style="margin-top: 0">本步事件</h3>
          <p style="margin: 8px 0">
            <n-tag size="small" :type="eventTagType(current.event_type)">
              v{{ current.version }} · {{ current.event_type }}
            </n-tag>
          </p>
          <div class="muted">actor</div>
          <div>{{ current.actor }}</div>
          <div class="muted" style="margin-top: 8px">occurred_at</div>
          <div>{{ formatTime(current.occurred_at) }}</div>
        </div>

        <div class="card">
          <h3 style="margin-top: 0">该步之后的状态</h3>
          <p style="margin: 8px 0">
            <n-tag size="small" :type="statusTagType">{{ statusLabel }}</n-tag>
          </p>
          <div class="grid-2">
            <div>
              <div class="muted">度量条数</div>
              <div style="font-size: 20px">{{ current.metric_count }}</div>
            </div>
            <div>
              <div class="muted">附件件数</div>
              <div style="font-size: 20px">{{ current.artifact_count }}</div>
            </div>
          </div>
          <template v-if="current.finished_at">
            <div class="muted" style="margin-top: 8px">finished_at</div>
            <div>{{ formatTime(current.finished_at) }}</div>
          </template>
          <p v-if="current.result_summary" style="margin-bottom: 0">
            <strong>结果：</strong>{{ current.result_summary }}
          </p>
          <p v-if="current.abort_reason" style="margin-bottom: 0">
            <strong>中止原因：</strong>{{ current.abort_reason }}
          </p>
        </div>
      </div>
    </template>

    <div v-else-if="loadingReplay" class="card"><n-spin /></div>
    <div v-else class="card muted">请先在上方选择一个 Run。</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { getReplay, listRuns } from '../api/client'

const route = useRoute()
const message = useMessage()

const runs = ref([])
const loadingRuns = ref(false)
const selectedRun = ref(null)
const replay = ref(null)
const loadingReplay = ref(false)
const stepIndex = ref(0)

const statusMap = {
  running: { type: 'info', label: '进行中' },
  completed: { type: 'success', label: '已完成' },
  aborted: { type: 'warning', label: '已中止' },
}

const runOptions = computed(() =>
  runs.value.map((r) => {
    const m = statusMap[r.status] || { label: r.status }
    return { label: `${r.project} / ${r.name}（${m.label} · v${r.version}）`, value: r.id }
  }),
)

const current = computed(() => replay.value.steps[stepIndex.value])
const progressPct = computed(() =>
  replay.value.total_versions > 1
    ? Math.round(((stepIndex.value + 1) / replay.value.total_versions) * 100)
    : 100,
)
const statusLabel = computed(
  () => (statusMap[current.value.status] || {}).label || current.value.status,
)
const statusTagType = computed(
  () => (statusMap[current.value.status] || {}).type || 'default',
)

function eventTagType(t) {
  if (t === 'RunCompleted') return 'success'
  if (t === 'RunAborted') return 'warning'
  if (t === 'RunStarted') return 'info'
  return 'default'
}

function formatTime(v) {
  return v ? new Date(v).toLocaleString() : '—'
}

function stepForward() {
  if (replay.value && stepIndex.value < replay.value.steps.length - 1) {
    stepIndex.value += 1
  }
}

function reset() {
  stepIndex.value = 0
}

async function onSelectRun(id) {
  if (!id) {
    replay.value = null
    return
  }
  loadingReplay.value = true
  try {
    const data = await getReplay(id)
    if (!data.steps.length) {
      replay.value = null
      message.warning('该 Run 暂无事件可回放')
      return
    }
    replay.value = data
    stepIndex.value = 0
  } catch (e) {
    replay.value = null
    message.error(e.message || '加载回放失败')
  } finally {
    loadingReplay.value = false
  }
}

onMounted(async () => {
  loadingRuns.value = true
  try {
    runs.value = await listRuns()
    const preset = route.query.run
    if (preset && runs.value.some((r) => r.id === preset)) {
      selectedRun.value = preset
      await onSelectRun(preset)
    }
  } catch (e) {
    message.error(e.message || '加载 Run 列表失败')
  } finally {
    loadingRuns.value = false
  }
})
</script>
