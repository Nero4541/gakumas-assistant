<script setup>
import apis from "@/scripts/apis.js";
import app from "@/main.js";

const props = defineProps({
  data: Object,
  label: {
    type: String,
    default: "物品选择"
  }
})

const items = ref([])
apis.get_all_item().then(res => {
  items.value = res.data
})

function filter(value, queryText, item) {
  const toLowerCaseString = val =>
    String(val != null ? val : '').toLowerCase()
  const query = toLowerCaseString(queryText)
  return item.raw.name.includes(query) || item.raw.translation?.name.includes(query)
}
</script>

<template>
  <v-autocomplete
    v-model="data.daily_buy_list.value"
    :items="items"
    item-value="id"
    :label="label"
    hide-no-data
    multiple
    clearable
    :custom-filter="filter"
  >
    <template v-slot:item="{ item, props }">
      <v-list-item @click="props.onClick" class="select_item">
        <template v-slot:prepend>
          <v-img
            v-if="item.raw.image"
            :src="`/api/clip_image/items/${item.raw.id}.png`"
            width="48"
            height="48"
          />
        </template>
        <div class="item-content">
          <div class="item-title">
            {{ item.raw.translation?.name || item.raw.name }}
            <span v-if="item.raw.translation?.name" class="item-subtitle">({{ item.raw.name }})</span>
          </div>

          <div class="item-description">
            {{ item.raw.translation?.description || item.raw.description }}
          </div>

          <div class="item-route">
            {{ item.raw.translation?.acquisitionRouteDescription || item.raw.acquisitionRouteDescription }}
          </div>
        </div>
      </v-list-item>
    </template>

    <template v-slot:selection="{ item, index }">
      <v-chip
        :text="item.raw.translation?.name || item.raw.name"
        size="small"
        :color="app.config.globalProperties.$theme.color"
      >
        <template v-slot:prepend>
          <v-img
            v-if="item.raw.image"
            :src="`/api/clip_image/items/${item.raw.id}.png`"
            width="24"
            height="24"
            class="mr-2"
          />
        </template>
      </v-chip>
    </template>
  </v-autocomplete>
</template>

<style scoped>
.select_item {
  display: flex;
  align-items: flex-start; /* 顶部对齐文字和图片 */
  padding: 8px 12px;
  gap: 12px; /* 图片与文字间距 */
}

.item-image {
  flex: 0 0 auto; /* 固定图片大小 */
}

.item-content {
  flex: 1; /* 文字区域自适应剩余宽度 */
  display: flex;
  flex-direction: column;
  gap: 4px; /* 文字行间距 */
}

.item-title {
  font-size: 15px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
}

.item-subtitle {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.65);
  margin-left: 4px;
}

.item-description {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.75);
  line-height: 1.3;
}

.item-route {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.2;
}

</style>
