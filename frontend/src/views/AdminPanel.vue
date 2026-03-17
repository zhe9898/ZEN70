<template>
  <div v-if="auth.isAdmin" class="container mx-auto py-4">
    <h1 class="text-2xl font-bold mb-4">控制台</h1>
    <UserManagementCard />
    <CardContainer :items="[]" source-type="local" />
  </div>
  <div v-else class="container mx-auto py-4">
    <p class="text-base-content/70">无权限访问控制台</p>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from "@/stores/auth";
import CardContainer from "@/components/CardContainer.vue";
import UserManagementCard from "@/components/UserManagementCard.vue";

const auth = useAuthStore();
</script>
