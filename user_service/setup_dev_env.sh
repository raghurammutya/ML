#!/bin/bash

echo "=========================================="
echo "User Service - Development Setup"
echo "=========================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env with your configuration:"
    echo "   - DATABASE_URL"
    echo "   - REDIS_URL"
    echo "   - JWT_SIGNING_KEY_ID"
    echo "   - JWT_ISSUER"
    echo "   - JWT_AUDIENCE"
    echo ""
else
    echo "✅ .env file exists"
fi

# Check if keys directory exists
if [ ! -d keys ]; then
    echo "📁 Creating keys directory..."
    mkdir -p keys
    echo "✅ Created keys directory"
fi

# Check if JWT keys exist
if [ ! -f keys/jwt_private.pem ] || [ ! -f keys/jwt_public.pem ]; then
    echo "🔐 Generating JWT keys..."
    openssl genrsa -out keys/jwt_private.pem 2048 2>/dev/null
    openssl rsa -in keys/jwt_private.pem -pubout -out keys/jwt_public.pem 2>/dev/null
    echo "✅ Generated JWT keys (keys/jwt_private.pem, keys/jwt_public.pem)"
else
    echo "✅ JWT keys exist"
fi

# Check if master key exists
if [ ! -f keys/master.key ]; then
    echo "🔐 Generating master encryption key..."
    python3 -c "import secrets; print(secrets.token_hex(32))" > keys/master.key
    echo "✅ Generated master key (keys/master.key)"
else
    echo "✅ Master key exists"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Edit .env with your configuration"
echo "2. Start PostgreSQL and Redis:"
echo "   docker-compose up -d timescaledb redis"
echo ""
echo "3. Run database migrations:"
echo "   alembic upgrade head"
echo ""
echo "4. Start the service:"
echo "   uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"
echo ""
echo "5. Visit API docs:"
echo "   http://localhost:8001/docs"
echo ""

