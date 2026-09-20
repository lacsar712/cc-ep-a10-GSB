<template>
  <div class="page">
    <div>
      <h1 style="margin-bottom: 4px">事件回放（只读演示）</h1>
      <p class="muted" style="margin-top: 0">
        选定 Run 后从第 1 版起，每次只前进一版，查看该步事件应用之后的临时状态。
      </p>
    </div>

    <div class="card" style="margin-bottom: 16px">
      <n-form-item label="选择 Run" :show-feedback="false" style="margin-bottom: 0">
        <n-select
          v-model:value="runId"
          :options="runOptions"
          filterable
          placeholder="选择要回放的 Run"
          style="max-width: 520px"
          @update:value="onSelectRun"
        />
      </n-form-item>
    </div>

    <template v-if="runId">
      <n-alert type="info" :show-icon="true" class="replay-alert">
        只读回放：当前状态由 <span class="mono">event_store</span> 前 {{ snap?.version ?? 0 }}
        条事件在<b>服务端内存中临时折叠</b>得到，不读取、不写入
        <span class="mono">run_projections</span> 正式投影；不产生任何命令或事件。「复位」回到第 1 版。
      </n-alert>

      <n-spin :show="loading">
        <div v-if="snap" class="card" style="margin-bottom: 16px">
          <div class="replay-controls">
            <div>
              <div class="muted" style="font-size: 13px">回放位置</div>
              <div style="font-size: 22px; font-weight: 700">
                v{{ snap.version }}
                <span class="muted" style="font-size: 14px; font-weight: 400">
                  / 共 {{ snap.total_versions }} 版
                </span>
              </div>
            </div>
            <div class="replay-buttons">
              <n-button :disabled="snap.version <= 1 || loading" @click="step(-1)">
                上一步
              </n-button>
              <n-button
                type="primary"
                :disabled="snap.at_end || loading"
                @click="step(1)"
              >
                前进一步
              </n-button>
              <n-button :disabled="snap.version <= 1 || loading" @click="reset">
                复位到 v1
              </n-button>
            </div>
          </div>

          <n-progress
            type="line"
            :percentage="percent"
            :height="6"
            :show-indicator="false"
            style="margin: 12px 0 4px"
          />

          <div class="current-event">
            <n-tag size="small" :type="eventTagType(snap.current_event.event_type)">
              v{{ snap.current_event.version }} · {{ snap.current_event.event_type }}
            </n-tag>
            <span class="muted" style="font-size: 13px">
              本步事件由 {{ snap.current_event.actor }} 于
              {{ formatTime(snap.current_event.occurred_at) }} 追加
            </span>
          </div>
        </div>

        <div v-if="snap" class="replay-columns">
          <!-- 回放临时状态 -->
          <div class="card replay-snapshot">
            <h3 style="margin-top: 0">回放临时状态（v{{ snap.version }} 之后）</h3>
            <div class="stat-row">
              <div class="stat-box">
                <div class="stat-value">
                  <n-tag :type="statusType(snap.status)" size="small">{{ statusLabel(snap.status) }}</n-tag>
                </div>
                <div class="stat-label">状态</div>
              </div>
              <div class="stat-box">
                <div class="stat-value">{{ snap.metric_count }}</div>
                <div class="stat-label">度量条数</div>
              </div>
              <div class="stat-box">
                <div class="stat-value">{{ snap.artifact_count }}</div>
                <div class="stat-label">附件件数</div>
              </div>
            </div>

            <div class="kv">
              <div><span class="muted">Run：</span>{{ snap.project }} / {{ snap.name }}</div>
              <div><span class="muted">开始：</span>{{ formatTime(snap.started_at) }}（{{ snap.started_by }}）</div>
              <div>
                <span class="muted">结束：</span>{{ snap.finished_at ? formatTime(snap.finished_at) : '—' }}
              </div>
              <p v-if="snap.result_summary" style="margin: 8px 0 0">
                <strong>结果：</strong>{{ snap.result_summary }}
              </p>
              <p v-if="snap.abort_reason" style="margin: 8px 0 0">
                <strong>中止原因：</strong>{{ snap.abort_reason }}
              </p>
            </div>

            <div class="snapshot-lists">
              <div>
                <div class="muted list-title">度量（{{ snap.metric_count }}）</div>
                <n-data-table
                  size="small"
                  :columns="metricCols"
                  :data="snap.metrics"
                  :bordered="false"
                />
              </div>
              <div>
                <div class="muted list-title">附件（{{ snap.artifact_count }}）</div>
                <n-data-table
                  size="small"
                  :columns="artifactCols"
                  :data="snap.artifacts"
                  :bordered="false"
                />
              </div>
            </div>
          </div>

          <!-- 正式投影当前状态（不受回放影响） -->
          <div class="card replay-official">
            <h3 style="margin-top: 0">
              正式投影当前值
              <span class="muted" style="font-size: 12px; font-weight: 400">（回放全程不变）</span>
            </h3>
            <div v-if="official" class="stat-row">
              <div class="stat-box">
                <div class="stat-value">
                  <n-tag :type="statusType(official.status)" size="small">
                    {{ statusLabel(official.status) }}
                  </n-tag>
                </div>
                <div class="stat-label">状态</div>
              </div>
              <div class="stat-box">
                <div class="stat-value">{{ official.metrics_json?.length ?? 0 }}</div>
                <div class="stat-label">度量条数</div>
              </div>
              <div class="stat-box">
                <div class="stat-value">{{ official.artifacts_json?.length ?? 0 }}</div>
                <div class="stat-label">附件件数</div>
              </div>
            </div>
            <p v-if="official" class="muted" style="margin-bottom: 0; font-size: 13px">
              正式投影停留在 v{{ official.version }}；左侧回放折叠不会修改它。
            </p>
          </div>
        </div>
      </n-spin>
    </template>

    <div v-else class="card muted">请先在上方选择一个 Run 开始回放。</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { getReplay, getRun, listRuns } from '../api/client'

const route = useRoute()
const message = useMessage()

const runs = ref([])
const runId = ref(null)
const snap = ref(null)
const official = ref(null)
const loading = ref(false)

const runOptions = computed(() =>
  runs.value.map((r) => ({
    label: `${r.project} / ${r.name}（${statusLabel(r.status)}，v${r.version}）`,
    value: r.id,
  })),
)

const percent = computed(() => {
  if (!snap.value || !snap.value.total_versions) return 0
  return Math.round((snap.value.version / snap.value.total_versions) * 100)
})

const metricCols = [
  { title: 'name', key: 'name' },
  { title: 'value', key: 'value' },
  { title: 'step', key: 'step' },
]
const artifactCols = [
  { title: 'name', key: 'name' },
  { title: 'uri', key: 'uri', ellipsis: { tooltip: true } },
]

function statusLabel(s) {
  return { running: '进行中', completed: '已完成', aborted: '已中止' }[s] || s
}
function statusType(s) {
  return { running: 'info', completed: 'success', aborted: 'warning' }[s] || 'default'
}
function eventTagType(t) {
  if (t === 'RunCompleted') return 'success'
  if (t === 'RunAborted') return 'warning'
  if (t === 'RunStarted') return 'info'
  return 'default'
}
function formatTime(v) {
  return v ? new Date(v).toLocaleString() : '—'
}

async function fetchSnapshot(targetVersion) {
  if (!runId.value) return
  loading.value = true
  try {
    // 服务端纯内存折叠：每次只按 version 重算临时投影，前端不保存任何中间状态。
    const [snapshot, current] = await Promise.all([
      getReplay(runId.value, targetVersion),
      getRun(runId.value),
    ])
    snap.value = snapshot
    official.value = current
  } catch (e) {
    message.error(e.message || '回放加载失败')
  } finally {
    loading.value = false
  }
}

function onSelectRun() {
  snap.value = null
  official.value = null
  fetchSnapshot(1)
}

function step(delta) {
  if (!snap.value) return
  const next = snap.value.version + delta
  if (next < 1 || next > snap.value.total_versions) return
  fetchSnapshot(next)
}

function reset() {
  fetchSnapshot(1)
}

onMounted(async () => {
  try {
    runs.value = await listRuns()
    if (route.query.run && runs.value.some((r) => r.id === route.query.run)) {
      runId.value = route.query.run
      await fetchSnapshot(1)
    }
  } catch (e) {
    message.error(e.message || 'Run 列表加载失败')
  }
})
</script>

<style scoped>
.replay-alert {
  margin-bottom: 16px;
}

.replay-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.replay-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.current-event {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.replay-columns {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  align-items: start;
}

@media (max-width: 900px) {
  .replay-columns {
    grid-template-columns: 1fr;
  }
}

.stat-row {
  display: flex;
  gap: 12px;
  margin: 12px 0 16px;
  flex-wrap: wrap;
}

.stat-box {
  flex: 1;
  min-width: 96px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  text-align: center;
  background: #fafcfd;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
}

.stat-label {
  color: var(--muted);
  font-size: 12px;
  margin-top: 4px;
}

.kv {
  font-size: 14px;
  line-height: 1.9;
}

.snapshot-lists {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 16px;
}

@media (max-width: 700px) {
  .snapshot-lists {
    grid-template-columns: 1fr;
  }
}

.list-title {
  font-size: 13px;
  margin-bottom: 6px;
}
</style>
