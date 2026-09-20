<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <div v-if="!auth.token" class="login-shell">
          <router-view />
        </div>
        <div v-else class="app-shell">
          <aside class="sidebar">
            <div class="brand">科学实验溯源工作台</div>
            <nav class="sidebar-nav">
              <router-link to="/runs">Run 列表</router-link>
              <router-link v-if="auth.role === 'researcher'" to="/runs/new">新建 Run</router-link>
              <router-link to="/replay">事件回放</router-link>
            </nav>
            <div class="sidebar-footer">
              <div class="muted">{{ auth.username }}（{{ roleLabel }}）</div>
              <n-button size="small" quaternary @click="logout">退出</n-button>
            </div>
          </aside>
          <main class="content">
            <router-view />
          </main>
        </div>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { zhCN, dateZhCN } from 'naive-ui'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()

const roleLabel = computed(() => (auth.role === 'researcher' ? '研究员' : '审计员'))

function logout() {
  auth.logout()
  router.push('/login')
}
</script>
