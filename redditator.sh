#!/bin/bash
set -e

clear

IMAGE_NAME="redditator-python"
DOCKERFILE_PATH="./Dockerfile"
COMPOSE_FILE="./docker-compose.yml"

# colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

DOCKER_CMD=""

log_info() { echo -e "${BLUE}[info]${NC} $1"; }
log_ok() { echo -e "${GREEN}[ok]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
log_err() { echo -e "${RED}[error]${NC} $1"; }
log_step() { echo -e "${CYAN}[step]${NC} $1"; }

export DOCKER_BUILDKIT=1
OS_TYPE=$(uname)
log_info "detected os: $OS_TYPE"

# check if running in container - more reliable method
is_container() {
    if [ -f /.dockerenv ]; then
        return 0
    fi
    if [ -f /proc/1/cgroup ]; then
        if grep -q "docker" /proc/1/cgroup 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

container_entrypoint() {
    log_step "starting redditator application in container"
    
    log_info "starting ollama service..."
    ollama serve > /dev/null 2>&1 &
    OLLAMA_PID=$!
    
    # wait for ollama to be ready 
    until ollama ps > /dev/null 2>&1; do
        sleep 1
    done
    
    log_ok "ollama ready"
    
    # run main application
    log_step "starting python application"
    cd /app && python3 src/main.py
    
    # cleanup
    log_info "shutting down..."
    kill $OLLAMA_PID 2>/dev/null || true
    wait $OLLAMA_PID 2>/dev/null || true
    log_ok "shutdown complete"
    exit 0
}

configure_services() {
    log_info "configuring docker services"
    sudo systemctl stop docker.socket docker.service 2>/dev/null || true
    sudo systemctl disable docker.socket 2>/dev/null || true
    sudo systemctl enable docker.service
    sudo systemctl start docker
}

install_docker() {
    log_step "installing docker and dependencies"
    
    case "$OS_TYPE" in
        "Linux")
            if command -v apt &>/dev/null; then
                sudo apt update && sudo apt install -y docker.io curl
                docker_compose_url="https://github.com/docker/compose/releases/download/v2.21.0/docker-compose-$(uname -s)-$(uname -m)"
                sudo curl -L "$docker_compose_url" -o /usr/local/bin/docker-compose
                sudo chmod +x /usr/local/bin/docker-compose
            elif command -v yum &>/dev/null; then
                sudo yum install -y docker curl
                docker_compose_url="https://github.com/docker/compose/releases/download/v2.21.0/docker-compose-$(uname -s)-$(uname -m)"
                sudo curl -L "$docker_compose_url" -o /usr/local/bin/docker-compose
                sudo chmod +x /usr/local/bin/docker-compose
            elif command -v pacman &>/dev/null; then
                sudo pacman -Syu --noconfirm docker curl
                docker_compose_url="https://github.com/docker/compose/releases/download/v2.21.0/docker-compose-$(uname -s)-$(uname -m)"
                sudo curl -L "$docker_compose_url" -o /usr/local/bin/docker-compose
                sudo chmod +x /usr/local/bin/docker-compose
            else
                log_err "unsupported linux distro"
                exit 1
            fi
            configure_services
            ;;
        "Darwin")
            log_err "install docker desktop from https://docker.com/products/docker-desktop"
            exit 1
            ;;
        *)
            log_err "unsupported os"
            exit 1
            ;;
    esac
}

DOCKER_FAILED=0

load_docker_cmd() {
    if docker info &>/dev/null; then
        DOCKER_CMD="docker"
        log_ok "using docker without sudo"
    elif sudo docker info &>/dev/null; then
        DOCKER_CMD="sudo docker"
        log_warn "using docker with sudo"
    else
        if [ "$DOCKER_FAILED" -eq 0 ]; then
            DOCKER_FAILED=1
            log_warn "docker not available, configuring services..."
            configure_services
            sleep 2
            load_docker_cmd
        elif [ "$DOCKER_FAILED" -eq 1 ]; then
            DOCKER_FAILED=2
            log_warn "docker still not available, installing docker..."
            install_docker
            sleep 2
            load_docker_cmd
        else
            log_err "docker not available after multiple attempts"
            exit 1
        fi
    fi
}

check_docker_group() {
    if ! docker info &>/dev/null && [[ "$OS_TYPE" == "Linux" ]]; then
        log_warn "adding user to docker group"
        sudo usermod -aG docker $USER
        log_info "please log out and log back in or run: newgrp docker"
        log_info "then restart this script"
        exit 1
    fi
}

host_mode() {
    log_step "running in host mode"

    load_docker_cmd
    check_docker_group

    if ! command -v docker-compose &>/dev/null && ! $DOCKER_CMD compose version &>/dev/null; then
        log_warn "docker-compose not found, installing..."
        install_docker
    fi

    case "${1:-}" in
        "--cleanup")
            log_step "cleaning docker resources"
            before=$(df --output=avail / | tail -1)
            $DOCKER_CMD ps -aq --filter "label=owner=redditator" | xargs -r $DOCKER_CMD rm -f &>/dev/null || true
            $DOCKER_CMD images -q --filter "label=owner=redditator" | xargs -r $DOCKER_CMD rmi -f &>/dev/null || true
            $DOCKER_CMD volume ls -q --filter "label=owner=redditator" | xargs -r $DOCKER_CMD volume rm -f &>/dev/null || true
            $DOCKER_CMD builder prune -af &>/dev/null || true
            freed=$(( ($(df --output=avail / | tail -1) - before)/1024/1024 ))
            log_ok "cleanup done - freed ~${freed}gb"
            exit 0
            ;;
        "--entrypoint")
            log_err "--entrypoint should only be used inside container"
            exit 1
            ;;
    esac

    BUILD_HASH_FILE=".docker_build_hash"
    current_hash=$(sha256sum "$DOCKERFILE_PATH" requirements 2>/dev/null | sha256sum | awk '{print $1}')

    DOCKER_COMPOSE="$DOCKER_CMD compose"
    if ! $DOCKER_COMPOSE version &>/dev/null; then
        DOCKER_COMPOSE="$DOCKER_CMD-compose"
    fi

    if [[ ! -f "$BUILD_HASH_FILE" ]] || [[ "$(cat "$BUILD_HASH_FILE" 2>/dev/null)" != "$current_hash" ]]; then
        log_step "building image"
        $DOCKER_COMPOSE -f "$COMPOSE_FILE" build
        echo "$current_hash" > "$BUILD_HASH_FILE"
    fi

    log_step "starting redditator container"
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" run --rm redditator
}

if is_container; then
    log_info "running in container mode"
    # in container, ignore all host logic and just run the app
    container_entrypoint
else
    host_mode "$@"
fi