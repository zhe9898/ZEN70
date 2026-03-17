import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/Login.vue"),
      meta: { title: "登录" },
    },
    {
      path: "/invite",
      name: "invite",
      component: () => import("@/views/InviteView.vue"),
      meta: { title: "数字家庭邀请" },
    },
    {
      path: "/",
      name: "admin",
      component: () => import("@/views/AdminPanel.vue"),
      meta: { title: "控制台", requiresAuth: true },
    },
    {
      path: "/family",
      name: "family",
      component: () => import("@/views/FamilyPanel.vue"),
      meta: { title: "家庭面板", requiresAuth: true },
    },
    {
      path: "/elderly",
      name: "elderly",
      component: () => import("@/views/ElderlyDashboard.vue"),
      meta: { title: "长辈模式", requiresAuth: true },
    },
    {
      path: "/gallery",
      name: "gallery",
      component: () => import("@/views/FamilyGallery.vue"),
      meta: { title: "极客相册", requiresAuth: true },
    },
    {
      path: "/emotion",
      name: "emotion",
      component: () => import("@/views/EmotionAlbum.vue"),
      meta: { title: "情感相册", requiresAuth: true },
    },
    {
      path: "/kids",
      name: "kids",
      component: () => import("@/views/KidsMode.vue"),
      meta: { title: "儿童模式", requiresAuth: true },
    },
    {
      path: "/media",
      name: "media",
      component: () => import("@/views/MediaCenter.vue"),
      meta: { title: "媒体中心", requiresAuth: true },
    },
    {
      path: "/iot",
      name: "iot",
      component: () => import("@/views/SmartHome.vue"),
      meta: { title: "全屋智能中控", requiresAuth: true },
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("@/views/SystemSettings.vue"),
      meta: { title: "系统设置", requiresAuth: true },
    },
    {
      path: "/board",
      name: "board",
      component: () => import("@/views/FamilyBoard.vue"),
      meta: { title: "家族信标", requiresAuth: true },
    },
  ],
});

router.beforeEach((to, _from, next) => {
  const auth = useAuthStore();
  if (to.meta.requiresAuth && !auth.token) {
    next({ name: "login" });
  } else if (to.name === "login" && auth.token) {
    if (auth.isAdmin) {
      next({ name: "admin" });
    } else if (auth.isElder) {
      next({ name: "elderly" });
    } else if (auth.isChild) {
      next({ name: "kids" });
    } else {
      next({ name: "family" });
    }
  } else {
    next();
  }
});
