<template>
  <div class="app-shell">
    <header class="header">
      <h1>面向 RAG 的智能分段 Demo</h1>
      <p>上传文档并查看分段结果。</p>
    </header>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  margin: 0 auto;
  max-width: 1200px;
  padding: 24px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: #1f2937;
}

.header h1 {
  margin: 0;
  font-size: 28px;
}

.header p {
  margin: 8px 0 20px;
  color: #4b5563;
}
</style>
