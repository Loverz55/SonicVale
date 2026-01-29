# 修复计划

## 问题1：音量调节后需要滚动才能更新进度条

### 问题分析
在 `WaveCellPro.vue` 第164行存在语法错误，导致音量 watch 无法正常工作：
```javascript
watch(vol2x, v => ws && ws.setVolume(Math.max(0, Math.min(v ?? 1.0, 1.0))))
```

### 解决方案
1. 修复语法错误（多余的括号）
2. 在音量变化后手动触发波形重绘，确保进度条实时更新
3. 可能需要调用 `ws.drawer.fireEvent('redraw')` 或类似方法

### 修改文件
- `sonicvale-front/src/components/WaveCellPro.vue`

---

## 问题2：Shift 多选功能

### 需求描述
点击一个选项后按住 Shift 选择另一个，中间的所有选项会被全选

### 实现方案
1. 添加状态变量记录最后一次点击的行索引
2. 监听复选框的点击事件，检测是否按下了 Shift 键
3. 如果按下了 Shift，计算范围并选中中间所有行
4. 更新 `selectedLineIds` Set

### 实现细节
```javascript
// 新增状态
const lastClickedIndex = ref(null)

// 修改 toggleRowSelection 函数
function toggleRowSelection(id, event) {
  const currentIndex = displayedLines.value.findIndex(l => l.id === id)

  if (event && event.shiftKey && lastClickedIndex.value !== null) {
    // Shift 多选模式
    const start = Math.min(lastClickedIndex.value, currentIndex)
    const end = Math.max(lastClickedIndex.value, currentIndex)

    // 清空之前的选择（可选，根据需求决定）
    selectedLineIds.value.clear()

    // 选中范围内的所有行
    for (let i = start; i <= end; i++) {
      selectedLineIds.value.add(displayedLines.value[i].id)
    }
  } else {
    // 普通单选模式
    if (selectedLineIds.value.has(id)) {
      selectedLineIds.value.delete(id)
    } else {
      selectedLineIds.value.add(id)
    }
    lastClickedIndex.value = currentIndex
  }
}
```

### 修改文件
- `sonicvale-front/src/pages/ProjectDubbingDetail.vue`

---

## 实施步骤

### 步骤1：修复音量调节问题
1. 修复 `WaveCellPro.vue` 第164行的语法错误
2. 添加波形重绘逻辑确保进度条实时更新
3. 测试音量调节是否实时反映

### 步骤2：实现 Shift 多选功能
1. 在 `ProjectDubbingDetail.vue` 中添加 `lastClickedIndex` 状态
2. 修改 `toggleRowSelection` 函数支持 Shift 多选
3. 更新复选框的 `onChange` 事件传递 event 参数
4. 测试 Shift 多选功能

### 步骤3：测试验证
1. 测试音量调节后进度条是否实时更新
2. 测试 Shift 多选功能是否正常工作
3. 测试边界情况（反向选择、单选、全选等）
