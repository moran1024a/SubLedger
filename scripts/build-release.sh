#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '用法: %s VERSION\n' "$0" >&2
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

VERSION=$1
if [[ ! $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
  printf '错误：版本必须是安全的 SemVer 风格值，例如 0.1.3。\n' >&2
  exit 2
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
OUTPUT_DIR=$ROOT_DIR/dist
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/subledger-release.XXXXXX")
ARCHIVE_NAME="subledger-${VERSION}.tar.gz"
CHECKSUM_NAME="${ARCHIVE_NAME}.sha256"
ARCHIVE_PATH=$OUTPUT_DIR/$ARCHIVE_NAME
CHECKSUM_PATH=$OUTPUT_DIR/$CHECKSUM_NAME
STAGE_ROOT=$WORK_DIR/subledger-$VERSION

cleanup() {
  rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf '错误：缺少命令 %s。\n' "$1" >&2
    exit 1
  fi
}

require_command cp
require_command cut
require_command dirname
require_command find
require_command grep
require_command head
require_command mkdir
require_command mktemp
require_command mv
require_command python3
require_command rm
require_command sed
require_command sha256sum
require_command tar
require_command gzip

if [[ -e $ARCHIVE_PATH || -e $CHECKSUM_PATH ]]; then
  printf '错误：发布产物已存在，不覆盖已有文件：%s 或 %s。\n' "$ARCHIVE_PATH" "$CHECKSUM_PATH" >&2
  exit 1
fi

read_project_version() {
  local value
  value=$(sed -nE 's/^version = "([^"]+)"/\1/p' "$ROOT_DIR/backend/pyproject.toml" | head -n 1)
  if [[ -z $value ]]; then
    printf '错误：无法读取 backend/pyproject.toml 的项目版本。\n' >&2
    exit 1
  fi
  printf '%s' "$value"
}

read_frontend_version() {
  python3 - "$ROOT_DIR/frontend/package.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    print(json.load(file)["version"])
PY
}

read_application_version() {
  local value
  value=$(sed -nE 's/.*FastAPI\(title="SubLedger", version="([^"]+)".*/\1/p' "$ROOT_DIR/backend/app/main.py" | head -n 1)
  if [[ -z $value ]]; then
    printf '错误：无法读取 backend/app/main.py 的应用版本。\n' >&2
    exit 1
  fi
  printf '%s' "$value"
}

check_version() {
  local name=$1
  local value=$2
  if [[ $value != "$VERSION" ]]; then
    printf '错误：%s 为 %s，与发布版本 %s 不一致。\n' "$name" "$value" "$VERSION" >&2
    exit 1
  fi
}

check_version 'backend/pyproject.toml' "$(read_project_version)"
check_version 'frontend/package.json' "$(read_frontend_version)"
check_version 'backend/app/main.py' "$(read_application_version)"

compose_file=$ROOT_DIR/docker-compose.yml
if grep -Eq 'MYSQL_|image:[[:space:]]*(mysql|mariadb)(:|[[:space:]]|$)|mysql-data|/var/lib/mysql|^[[:space:]]+mysql:' "$compose_file"; then
  printf '错误：docker-compose.yml 不能包含内置 MySQL、数据库初始化凭据或数据库卷。\n' >&2
  exit 1
fi
if grep -Fq './backend/config/config.toml:/app/config/config.toml:ro' "$compose_file"; then
  :
elif grep -Fq 'source: ./backend/config/config.toml' "$compose_file" \
  && grep -Fq 'target: /app/config/config.toml' "$compose_file" \
  && grep -Fq 'read_only: true' "$compose_file"; then
  :
else
  printf '错误：docker-compose.yml 缺少外部配置的安全只读挂载。\n' >&2
  exit 1
fi
onepanel_compose_file=$ROOT_DIR/docker-compose.1panel.yml
if grep -Eq 'MYSQL_|image:[[:space:]]*(mysql|mariadb)(:|[[:space:]]|$)|mysql-data|/var/lib/mysql|^[[:space:]]+mysql:' "$onepanel_compose_file"; then
  printf '错误：docker-compose.1panel.yml 不能包含内置 MySQL、数据库初始化凭据或数据库卷。\n' >&2
  exit 1
fi
if ! grep -Fq './backend/config/config.toml:/app/config/config.toml:ro' "$onepanel_compose_file"; then
  printf '错误：docker-compose.1panel.yml 缺少外部配置的安全只读挂载。\n' >&2
  exit 1
fi
if grep -Eq '^[[:space:]]+ports:' "$onepanel_compose_file"; then
  printf '错误：docker-compose.1panel.yml 不能映射宿主机端口。\n' >&2
  exit 1
fi
onepanel_network_names=$(sed -n '/^networks:$/,$p' "$onepanel_compose_file" \
  | sed -nE 's/^  ([^[:space:]][^:]*):$/\1/p')
if [[ $onepanel_network_names != '1panel-network' ]] \
  || ! grep -Fqx '    external: true' "$onepanel_compose_file" \
  || ! grep -Fqx '    name: 1panel-network' "$onepanel_compose_file" \
  || ! grep -Fqx '      - 1panel-network' "$onepanel_compose_file"; then
  printf '错误：docker-compose.1panel.yml 必须只复用外部 1panel-network。\n' >&2
  exit 1
fi
if ! grep -Fqx 'password = "change-this-password"' "$ROOT_DIR/backend/config/config.example.toml"; then
  printf '错误：config.example.toml 不再是示例配置模板，请从安全源码目录构建。\n' >&2
  exit 1
fi

copy_entries=(
  '.dockerignore'
  '.gitignore'
  'LICENSE'
  'README.md'
  'docker-compose.1panel.yml'
  'docker-compose.yml'
  'scripts/build-release.sh'
  'backend/.dockerignore'
  'backend/Dockerfile'
  'backend/README.md'
  'backend/alembic.ini'
  'backend/alembic'
  'backend/app'
  'backend/config/config.example.toml'
  'backend/docker/entrypoint.sh'
  'backend/pyproject.toml'
  'backend/tests'
  'frontend/.gitkeep'
  'frontend/.prettierrc.json'
  'frontend/README.md'
  'frontend/eslint.config.js'
  'frontend/index.html'
  'frontend/package.json'
  'frontend/pnpm-lock.yaml'
  'frontend/src'
  'frontend/tests'
  'frontend/tsconfig.json'
  'frontend/vite.config.ts'
  'frontend/vitest.config.ts'
)

mkdir -p -- "$STAGE_ROOT"
for relative_path in "${copy_entries[@]}"; do
  source_path=$ROOT_DIR/$relative_path
  target_path=$STAGE_ROOT/$relative_path
  if [[ ! -e $source_path && ! -L $source_path ]]; then
    printf '错误：发布包所需文件不存在：%s\n' "$relative_path" >&2
    exit 1
  fi
  if [[ -L $source_path ]]; then
    printf '错误：发布包输入不能是符号链接：%s\n' "$relative_path" >&2
    exit 1
  fi
  nested_link=$(find "$source_path" -type l -print -quit 2>/dev/null || true)
  if [[ -n $nested_link ]]; then
    printf '错误：发布包输入包含符号链接：%s\n' "${nested_link#$ROOT_DIR/}" >&2
    exit 1
  fi
  mkdir -p -- "$(dirname -- "$target_path")"
  cp -a -- "$source_path" "$target_path"
done

find "$STAGE_ROOT" -type d \( \
  -name '__pycache__' -o -name '.pytest_cache' -o -name '.vite' -o -name '.vite-temp' \
\) -prune -exec rm -rf -- {} +

for forbidden_path in \
  'backend/config/config.toml' \
  'backend/data' \
  'backend/logs' \
  'frontend/node_modules' \
  'frontend/dist' \
  '.venv' \
  'backend/.venv' \
  'dist'; do
  if [[ -e $STAGE_ROOT/$forbidden_path || -L $STAGE_ROOT/$forbidden_path ]]; then
    printf '错误：禁止的文件进入发布 staging：%s\n' "$forbidden_path" >&2
    exit 1
  fi
done

if find "$STAGE_ROOT" -type f \( \
  -name '*.pyc' -o -name '*.pyo' -o -name '*.key' -o -name '*.pem' -o \
  -name '*.log' -o -name '.env' -o -name '.env.*' -o -name '.coverage' \
\) -print -quit | grep -q .; then
  printf '错误：发布 staging 包含禁止的生成文件或敏感文件。\n' >&2
  exit 1
fi

mkdir -p -- "$OUTPUT_DIR"
TEMP_ARCHIVE=$OUTPUT_DIR/.${ARCHIVE_NAME}.tmp
TEMP_CHECKSUM=$OUTPUT_DIR/.${CHECKSUM_NAME}.tmp
rm -f -- "$TEMP_ARCHIVE" "$TEMP_CHECKSUM"

archive_members=$WORK_DIR/archive-members.txt
tar \
  --sort=name \
  --mtime='UTC 1970-01-01' \
  --owner=0 \
  --group=0 \
  --numeric-owner \
  -czf "$TEMP_ARCHIVE" \
  -C "$WORK_DIR" \
  "subledger-$VERSION"
tar -tzf "$TEMP_ARCHIVE" >"$archive_members"

while IFS= read -r member; do
  case $member in
    "subledger-$VERSION"|"subledger-$VERSION/"|"subledger-$VERSION"/*) ;;
    *)
      printf '错误：归档包含越界路径：%s\n' "$member" >&2
      exit 1
      ;;
  esac
  case $member in
    /*|*'../'*|*/config.toml|*/.env|*/.env.*|*/node_modules|*/node_modules/*|*/dist|*/dist/*|*/.venv|*/.venv/*|*/__pycache__|*/__pycache__/*|*/.pytest_cache|*/.pytest_cache/*|*.pyc|*.pyo|*.key|*.pem|*.log)
      printf '错误：归档包含禁止内容：%s\n' "$member" >&2
      exit 1
      ;;
  esac
done <"$archive_members"

required_members=(
  "subledger-$VERSION/docker-compose.1panel.yml"
  "subledger-$VERSION/docker-compose.yml"
  "subledger-$VERSION/backend/Dockerfile"
  "subledger-$VERSION/backend/pyproject.toml"
  "subledger-$VERSION/backend/config/config.example.toml"
  "subledger-$VERSION/frontend/package.json"
  "subledger-$VERSION/frontend/pnpm-lock.yaml"
)
for member in "${required_members[@]}"; do
  if ! grep -Fqx "$member" "$archive_members"; then
    printf '错误：归档缺少必要文件：%s\n' "$member" >&2
    exit 1
  fi
done

mv -- "$TEMP_ARCHIVE" "$ARCHIVE_PATH"
printf '%s  %s\n' "$(sha256sum "$ARCHIVE_PATH" | cut -d ' ' -f 1)" "$ARCHIVE_NAME" >"$TEMP_CHECKSUM"
mv -- "$TEMP_CHECKSUM" "$CHECKSUM_PATH"

printf '已生成源码发布包：%s\n' "$ARCHIVE_PATH"
printf '已生成 SHA-256 校验文件：%s\n' "$CHECKSUM_PATH"
printf '校验命令：cd %s && sha256sum -c %s\n' "$OUTPUT_DIR" "$CHECKSUM_NAME"
