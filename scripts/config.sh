#!/bin/bash
set -e

# Configuration management script
# Usage: ./config.sh [show|edit|validate] [dev|prod]

ACTION=${1:-show}
ENVIRONMENT=${2:-dev}

ENV_FILE=".env.$ENVIRONMENT"

case $ACTION in
    "show")
        echo "📄 Configuration for $ENVIRONMENT environment:"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        if [[ -f "$ENV_FILE" ]]; then
            cat "$ENV_FILE" | grep -v "^#" | grep -v "^$" | sort
        else
            echo "❌ Environment file $ENV_FILE not found"
            exit 1
        fi
        ;;
    "edit")
        echo "✏️  Editing $ENVIRONMENT configuration..."
        ${EDITOR:-nano} "$ENV_FILE"
        echo "✅ Configuration updated. Run './scripts/deploy.sh $ENVIRONMENT' to apply changes."
        ;;
    "validate")
        echo "🔍 Validating $ENVIRONMENT configuration..."
        if [[ ! -f "$ENV_FILE" ]]; then
            echo "❌ Environment file $ENV_FILE not found"
            exit 1
        fi
        
        # Check required variables
        REQUIRED_VARS=(
            "DATABASE_URL"
            "REDIS_URL"
            "BACKEND_PORT"
            "FRONTEND_PORT"
            "ENVIRONMENT"
            "BACKEND_SERVICE_NAME"
            "FRONTEND_SERVICE_NAME"
        )
        
        source "$ENV_FILE"
        MISSING_VARS=()
        
        for var in "${REQUIRED_VARS[@]}"; do
            if [[ -z "${!var}" ]]; then
                MISSING_VARS+=("$var")
            fi
        done
        
        if [[ ${#MISSING_VARS[@]} -eq 0 ]]; then
            echo "✅ Configuration is valid"
        else
            echo "❌ Missing required variables: ${MISSING_VARS[*]}"
            exit 1
        fi
        ;;
    "diff")
        echo "🔍 Comparing dev and prod configurations..."
        if [[ -f ".env.dev" && -f ".env.prod" ]]; then
            echo "Differences between dev and prod:"
            diff -u .env.dev .env.prod || true
        else
            echo "❌ Both .env.dev and .env.prod files must exist"
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 [show|edit|validate|diff] [dev|prod]"
        echo ""
        echo "Actions:"
        echo "  show     - Display current configuration"
        echo "  edit     - Edit configuration file"
        echo "  validate - Validate configuration"
        echo "  diff     - Compare dev and prod configurations"
        exit 1
        ;;
esac