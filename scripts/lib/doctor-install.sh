#!/usr/bin/env bash
# Install recipes sourced by scripts/doctor.sh — pure function
# definitions, no top-level side effects, so doctor stays under the
# bash code-line limit (#242) and the recipes stay greppable in one
# place.
# shellcheck shell=bash

detect_pkg_manager() {
    if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
        echo brew
    elif command -v apt-get >/dev/null 2>&1; then
        echo apt
    elif command -v apt >/dev/null 2>&1; then
        echo apt
    else
        echo unknown
    fi
}

manual_install_hint() {
    local tool=$1
    case "$tool" in
        git) echo "Install git via your platform package manager." ;;
        gh) echo "brew install gh  OR  sudo apt-get install -y gh" ;;
        npx) echo "brew install node  OR  sudo apt-get install -y npm" ;;
        uvx) echo "brew install uv  OR  curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
        prek) echo "brew install prek  OR  see https://github.com/j178/prek#installation" ;;
        *) echo "Install $tool manually." ;;
    esac
}

install_tool() {
    local tool=$1
    local mgr
    mgr=$(detect_pkg_manager)

    if [[ "$mgr" == unknown ]]; then
        echo "Cannot auto-install $tool: unrecognized platform or package manager."
        manual_install_hint "$tool"
        return 1
    fi

    case "$tool" in
        git)
            case "$mgr" in
                brew) brew install git ;;
                apt) sudo apt-get install -y git ;;
            esac
            ;;
        gh)
            case "$mgr" in
                brew) brew install gh ;;
                apt) sudo apt-get install -y gh ;;
            esac
            ;;
        npx)
            case "$mgr" in
                brew) brew install node ;;
                apt) sudo apt-get install -y npm ;;
            esac
            ;;
        uvx)
            case "$mgr" in
                brew) brew install uv ;;
                apt) curl -LsSf https://astral.sh/uv/install.sh | sh ;;
            esac
            ;;
        prek)
            if command -v uv >/dev/null 2>&1; then
                uv tool install prek
            else
                case "$mgr" in
                    brew) brew install prek ;;
                    apt)
                        echo "Cannot auto-install prek via apt (and uv is missing)."
                        manual_install_hint prek
                        return 1
                        ;;
                esac
            fi
            ;;
        *)
            echo "No install recipe for $tool."
            return 1
            ;;
    esac
}
