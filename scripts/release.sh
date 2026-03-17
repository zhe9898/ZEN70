#!/usr/bin/env bash
# ZEN70 发布脚本：预检、打 tag、构建镜像、更新文档
# 用法: ./scripts/release.sh [版本号]
# 版本号可选，未提供时从 CHANGELOG/Conventional Commits 推断
# 法典 5.2.3：禁止人工打 Tag；必须通过本脚本或 CI 自动打 Tag，遵循 Conventional Commits。
# 依赖: git, docker, 需已配置 REGISTRY_* 环境变量

set -e

cd "$(dirname "$0")/.."
ROOT=$(pwd)

# 预检
check_workspace() {
  if ! git diff-index --quiet HEAD --; then
    echo "[FATAL] Workspace is dirty! 必须提交所有本地更改后才能执行发布流程。"
    echo "变更列表:"
    git diff --stat
    exit 1
  fi
}

check_ci() {
  if command -v gh &>/dev/null; then
    if ! gh run list --limit 1 --json conclusion --jq '.[0].conclusion' | grep -q 'success'; then
      echo "[WARN] 最近 CI 可能未通过，请确认后继续"
    fi
  fi
}

check_changelog() {
  if ! grep -q "## \[Unreleased\]" CHANGELOG.md 2>/dev/null; then
    echo "[WARN] CHANGELOG 中无 [Unreleased] 段"
  fi
}

infer_version() {
  local current
  current=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
  current=${current#v}
  # 简单递增 patch
  IFS='.' read -r ma mi pa <<< "$current"
  echo "${ma}.${mi}.$((pa + 1))"
}

main() {
  VERSION=${1:-$(infer_version)}
  VERSION=${VERSION#v}
  TAG="v${VERSION}"

  echo "=== ZEN70 Release $TAG ==="
  check_workspace
  check_ci
  check_changelog
  echo "将创建 tag: $TAG"
  read -r -p "继续? [y/N] " resp
  [[ "$resp" =~ ^[yY] ]] || exit 1

  git tag -a "$TAG" -m "Release $TAG"
  echo "Tag $TAG 已创建，推送到远程: git push origin $TAG"
}

main "$@"
