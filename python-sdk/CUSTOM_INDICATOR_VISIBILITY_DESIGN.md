# Custom Indicator Visibility & Sharing Design

## Overview

Custom indicators support **three visibility levels**:

1. **Private**: Only visible to the creator
2. **Shared**: Visible to specific users or groups
3. **Public**: Visible to all users on the platform

This enables:
- Personal indicators for proprietary trading strategies
- Team collaboration within organizations
- Community sharing of popular indicators
- Marketplace for premium indicators (future)

---

## Visibility Levels

### 1. Private (Default)

**Who Can See**: Only the creator

**Use Cases**:
- Proprietary trading indicators
- Personal experimental indicators
- Strategy-specific indicators you don't want to share

**Example**:
```python
# Create private indicator
client.indicators.create_custom_indicator(
    name="MY_SECRET_RSI",
    display_name="My Secret RSI Strategy",
    description="Proprietary RSI variant",
    code=indicator_code,
    parameters=[...],
    visibility="private"  # Default
)
```

**API Response**:
```json
{
  "name": "MY_SECRET_RSI",
  "visibility": "private",
  "created_by": "user@example.com",
  "created_at": "2025-11-04T10:30:00Z",
  "shared_with": []
}
```

---

### 2. Shared (Group/User Level)

**Who Can See**: Creator + specified users/groups

**Use Cases**:
- Team indicators within a trading firm
- Family/friends indicator sharing
- Beta testing new indicators with select users
- Paid groups (subscriptions)

**Share with Specific Users**:
```python
# Share with specific users
client.indicators.share_indicator(
    indicator_name="MY_TEAM_RSI",
    share_with_users=[
        "alice@example.com",
        "bob@example.com",
        "carol@example.com"
    ]
)
```

**Share with Groups**:
```python
# Share with a group
client.indicators.share_indicator(
    indicator_name="MY_TEAM_RSI",
    share_with_groups=[
        "trading-team-alpha",
        "quant-research-group"
    ]
)
```

**API Response**:
```json
{
  "name": "MY_TEAM_RSI",
  "visibility": "shared",
  "created_by": "admin@example.com",
  "created_at": "2025-11-04T10:30:00Z",
  "shared_with": {
    "users": [
      "alice@example.com",
      "bob@example.com",
      "carol@example.com"
    ],
    "groups": [
      "trading-team-alpha",
      "quant-research-group"
    ]
  },
  "permissions": {
    "can_view": true,
    "can_use": true,
    "can_edit": false,  # Only creator can edit
    "can_reshare": false
  }
}
```

---

### 3. Public

**Who Can See**: All platform users

**Use Cases**:
- Community-contributed indicators
- Open-source indicators
- Educational indicators
- Marketplace indicators (with ratings/reviews)

**Example**:
```python
# Make indicator public
client.indicators.set_visibility(
    indicator_name="COMMUNITY_RSI",
    visibility="public",
    allow_forking=True  # Let others create variants
)
```

**API Response**:
```json
{
  "name": "COMMUNITY_RSI",
  "visibility": "public",
  "created_by": "expert@example.com",
  "created_at": "2025-11-04T10:30:00Z",
  "stats": {
    "users_count": 1247,
    "likes": 892,
    "forks": 45,
    "rating": 4.7
  },
  "tags": ["momentum", "community", "beginner-friendly"],
  "license": "MIT"
}
```

---

## Permissions Model

### Permission Types

| Permission | Private | Shared | Public |
|------------|---------|--------|--------|
| **can_view** | Creator only | Creator + shared users/groups | Everyone |
| **can_use** | Creator only | Creator + shared users/groups | Everyone |
| **can_edit** | Creator only | Creator only (unless admin) | Creator only |
| **can_delete** | Creator only | Creator only | Creator only |
| **can_reshare** | N/A | Creator sets policy | N/A |
| **can_fork** | N/A | Creator sets policy | Creator sets policy |

### Example Permission Policies

**Restrictive Sharing**:
```python
client.indicators.share_indicator(
    indicator_name="MY_TEAM_RSI",
    share_with_groups=["trading-team-alpha"],
    permissions={
        "can_view": True,
        "can_use": True,
        "can_edit": False,  # Only I can edit
        "can_reshare": False,  # Team members can't share further
        "can_fork": False  # No variants allowed
    }
)
```

**Collaborative Sharing**:
```python
client.indicators.share_indicator(
    indicator_name="TEAM_STRATEGY_RSI",
    share_with_groups=["quant-research-group"],
    permissions={
        "can_view": True,
        "can_use": True,
        "can_edit": True,  # Team can edit collaboratively
        "can_reshare": False,
        "can_fork": True  # Team can create variants
    }
)
```

**Open Public**:
```python
client.indicators.set_visibility(
    indicator_name="OPEN_SOURCE_RSI",
    visibility="public",
    permissions={
        "can_view": True,
        "can_use": True,
        "can_edit": False,  # Only I can edit original
        "can_reshare": True,  # Anyone can share
        "can_fork": True,  # Anyone can create variants
        "license": "MIT"  # Open source license
    }
)
```

---

## Database Schema

### custom_indicators Table

```sql
CREATE TABLE custom_indicators (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(50) NOT NULL,

    -- Code and configuration
    code TEXT NOT NULL,  -- Python code
    parameters JSONB NOT NULL,  -- Parameter definitions
    outputs JSONB NOT NULL,  -- Output field names

    -- Ownership and visibility
    created_by VARCHAR(255) NOT NULL REFERENCES users(email),
    visibility VARCHAR(20) NOT NULL DEFAULT 'private',  -- private, shared, public

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1,

    -- Stats (for public indicators)
    users_count INTEGER DEFAULT 0,
    likes_count INTEGER DEFAULT 0,
    forks_count INTEGER DEFAULT 0,
    rating DECIMAL(3,2) DEFAULT 0.0,

    -- Tags and categorization
    tags TEXT[],
    license VARCHAR(50),  -- MIT, Apache, Proprietary, etc.

    -- Permissions
    allow_forking BOOLEAN DEFAULT FALSE,
    allow_resharing BOOLEAN DEFAULT FALSE,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,  -- Admin verification for public indicators

    CONSTRAINT valid_visibility CHECK (visibility IN ('private', 'shared', 'public'))
);

CREATE INDEX idx_custom_indicators_created_by ON custom_indicators(created_by);
CREATE INDEX idx_custom_indicators_visibility ON custom_indicators(visibility);
CREATE INDEX idx_custom_indicators_category ON custom_indicators(category);
CREATE INDEX idx_custom_indicators_tags ON custom_indicators USING GIN(tags);
```

### indicator_shares Table

```sql
CREATE TABLE indicator_shares (
    id SERIAL PRIMARY KEY,
    indicator_name VARCHAR(100) NOT NULL REFERENCES custom_indicators(name) ON DELETE CASCADE,

    -- Shared with
    shared_with_user VARCHAR(255) REFERENCES users(email),  -- NULL if shared with group
    shared_with_group VARCHAR(100) REFERENCES user_groups(group_name),  -- NULL if shared with user

    -- Permissions
    can_view BOOLEAN DEFAULT TRUE,
    can_use BOOLEAN DEFAULT TRUE,
    can_edit BOOLEAN DEFAULT FALSE,
    can_reshare BOOLEAN DEFAULT FALSE,
    can_fork BOOLEAN DEFAULT FALSE,

    -- Metadata
    shared_by VARCHAR(255) NOT NULL REFERENCES users(email),
    shared_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Ensure at least one of user or group is set
    CONSTRAINT one_share_target CHECK (
        (shared_with_user IS NOT NULL AND shared_with_group IS NULL) OR
        (shared_with_user IS NULL AND shared_with_group IS NOT NULL)
    ),

    -- Unique sharing per user/group
    UNIQUE (indicator_name, shared_with_user),
    UNIQUE (indicator_name, shared_with_group)
);

CREATE INDEX idx_indicator_shares_indicator ON indicator_shares(indicator_name);
CREATE INDEX idx_indicator_shares_user ON indicator_shares(shared_with_user);
CREATE INDEX idx_indicator_shares_group ON indicator_shares(shared_with_group);
```

### user_groups Table

```sql
CREATE TABLE user_groups (
    id SERIAL PRIMARY KEY,
    group_name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    description TEXT,

    -- Ownership
    created_by VARCHAR(255) NOT NULL REFERENCES users(email),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Visibility
    is_public BOOLEAN DEFAULT FALSE,  -- Public groups anyone can join

    -- Stats
    member_count INTEGER DEFAULT 0,

    -- Status
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_user_groups_created_by ON user_groups(created_by);
CREATE INDEX idx_user_groups_is_public ON user_groups(is_public);
```

### group_members Table

```sql
CREATE TABLE group_members (
    id SERIAL PRIMARY KEY,
    group_name VARCHAR(100) NOT NULL REFERENCES user_groups(group_name) ON DELETE CASCADE,
    user_email VARCHAR(255) NOT NULL REFERENCES users(email) ON DELETE CASCADE,

    -- Roles
    role VARCHAR(20) NOT NULL DEFAULT 'member',  -- owner, admin, member

    -- Metadata
    joined_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (group_name, user_email),
    CONSTRAINT valid_role CHECK (role IN ('owner', 'admin', 'member'))
);

CREATE INDEX idx_group_members_group ON group_members(group_name);
CREATE INDEX idx_group_members_user ON group_members(user_email);
```

---

## API Endpoints

### Custom Indicator Management

#### Create Custom Indicator
```http
POST /indicators/custom/create
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "name": "MY_CUSTOM_RSI",
  "display_name": "My Custom RSI",
  "description": "Custom RSI with multiplier",
  "category": "momentum",
  "code": "def my_custom_rsi(ohlcv, length=10, multiplier=1.5):\n    ...",
  "parameters": [
    {"name": "length", "type": "integer", "default": 10, "min": 2, "max": 50},
    {"name": "multiplier", "type": "float", "default": 1.5, "min": 1.0, "max": 3.0}
  ],
  "outputs": ["MY_CUSTOM_RSI"],
  "visibility": "private",  // or "shared", "public"
  "allow_forking": false,
  "allow_resharing": false
}
```

#### List Indicators (respects visibility)
```http
GET /indicators/list?include_custom=true&visibility=all
Authorization: Bearer <JWT>

Response:
{
  "indicators": [
    // Built-in indicators (always visible)
    {...},

    // User's private indicators
    {"name": "MY_PRIVATE_RSI", "visibility": "private", "created_by": "me@example.com"},

    // Shared indicators (user has access)
    {"name": "TEAM_RSI", "visibility": "shared", "created_by": "admin@example.com", "shared_via": "trading-team-alpha"},

    // Public indicators
    {"name": "COMMUNITY_RSI", "visibility": "public", "created_by": "expert@example.com", "likes": 892}
  ]
}
```

#### Update Visibility
```http
PUT /indicators/custom/{indicator_name}/visibility
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "visibility": "public",
  "allow_forking": true,
  "allow_resharing": true,
  "license": "MIT"
}
```

#### Share Indicator
```http
POST /indicators/custom/{indicator_name}/share
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "share_with_users": ["alice@example.com", "bob@example.com"],
  "share_with_groups": ["trading-team-alpha"],
  "permissions": {
    "can_view": true,
    "can_use": true,
    "can_edit": false,
    "can_reshare": false,
    "can_fork": true
  }
}
```

#### Unshare Indicator
```http
DELETE /indicators/custom/{indicator_name}/share
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "unshare_from_users": ["bob@example.com"],
  "unshare_from_groups": ["old-team"]
}
```

#### Fork Indicator (Create Variant)
```http
POST /indicators/custom/{indicator_name}/fork
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "new_name": "MY_CUSTOM_RSI_V2",
  "display_name": "My Custom RSI V2",
  "modifications": "Added smoothing parameter",
  "visibility": "private"
}

Response:
{
  "status": "success",
  "indicator": {
    "name": "MY_CUSTOM_RSI_V2",
    "forked_from": "COMMUNITY_RSI",
    "original_author": "expert@example.com",
    "your_modifications": "Added smoothing parameter"
  }
}
```

### Group Management

#### Create Group
```http
POST /groups/create
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "group_name": "trading-team-alpha",
  "display_name": "Trading Team Alpha",
  "description": "Quantitative trading team",
  "is_public": false
}
```

#### Add Members to Group
```http
POST /groups/{group_name}/members
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "members": [
    {"email": "alice@example.com", "role": "admin"},
    {"email": "bob@example.com", "role": "member"}
  ]
}
```

---

## SDK Usage Examples

### Creating Indicators with Different Visibilities

```python
from stocksblitz import TradingClient

client = TradingClient.from_credentials(...)

# Private indicator (default)
client.indicators.create_custom_indicator(
    name="MY_PRIVATE_RSI",
    display_name="My Private RSI",
    code=indicator_code,
    parameters=[...],
    visibility="private"
)

# Shared with team
client.indicators.create_custom_indicator(
    name="TEAM_STRATEGY_RSI",
    display_name="Team Strategy RSI",
    code=indicator_code,
    parameters=[...],
    visibility="shared",
    share_with_groups=["trading-team-alpha"]
)

# Public indicator
client.indicators.create_custom_indicator(
    name="COMMUNITY_RSI",
    display_name="Community RSI",
    code=indicator_code,
    parameters=[...],
    visibility="public",
    allow_forking=True,
    license="MIT"
)
```

### Listing Indicators by Visibility

```python
# List only my private indicators
my_indicators = client.indicators.list_indicators(
    category="custom",
    visibility="private"
)

# List shared indicators I have access to
shared_indicators = client.indicators.list_indicators(
    category="custom",
    visibility="shared"
)

# List public indicators
public_indicators = client.indicators.list_indicators(
    category="custom",
    visibility="public"
)

# List all indicators I can use
all_indicators = client.indicators.list_indicators(
    category="custom",
    visibility="all"  # private + shared + public
)
```

### Sharing and Permissions

```python
# Share with specific users
client.indicators.share_indicator(
    indicator_name="MY_TEAM_RSI",
    share_with_users=["alice@example.com", "bob@example.com"],
    permissions={
        "can_view": True,
        "can_use": True,
        "can_edit": False,
        "can_fork": True
    }
)

# Share with a group
client.indicators.share_indicator(
    indicator_name="MY_TEAM_RSI",
    share_with_groups=["trading-team-alpha"]
)

# Unshare
client.indicators.unshare_indicator(
    indicator_name="MY_TEAM_RSI",
    unshare_from_users=["bob@example.com"]
)

# Change visibility
client.indicators.set_visibility(
    indicator_name="MY_PRIVATE_RSI",
    visibility="public",
    allow_forking=True
)
```

### Forking Public Indicators

```python
# Fork a public indicator to create your own variant
client.indicators.fork_indicator(
    source_indicator="COMMUNITY_RSI",
    new_name="MY_ENHANCED_RSI",
    display_name="My Enhanced RSI",
    modifications="Added smoothing and threshold parameters"
)

# Your fork is private by default
# You can then modify it
client.indicators.update_custom_indicator(
    indicator_name="MY_ENHANCED_RSI",
    code=new_code,
    parameters=new_parameters
)
```

---

## Frontend Integration

### Indicator Picker UI

```typescript
// Fetch indicators with visibility
const response = await fetch('/indicators/list?include_custom=true&visibility=all', {
  headers: { 'Authorization': `Bearer ${token}` }
});

const { indicators } = await response.json();

// Group by visibility
const privateIndicators = indicators.filter(ind => ind.visibility === 'private');
const sharedIndicators = indicators.filter(ind => ind.visibility === 'shared');
const publicIndicators = indicators.filter(ind => ind.visibility === 'public');

// Render tabs
<Tabs>
  <Tab label="My Indicators">
    {privateIndicators.map(ind => (
      <IndicatorCard
        indicator={ind}
        actions={['edit', 'delete', 'share']}
      />
    ))}
  </Tab>

  <Tab label="Shared with Me">
    {sharedIndicators.map(ind => (
      <IndicatorCard
        indicator={ind}
        sharedBy={ind.created_by}
        sharedVia={ind.shared_via}  // "trading-team-alpha"
        actions={['use', 'fork']}
      />
    ))}
  </Tab>

  <Tab label="Community">
    {publicIndicators.map(ind => (
      <IndicatorCard
        indicator={ind}
        stats={{
          users: ind.users_count,
          likes: ind.likes_count,
          rating: ind.rating
        }}
        actions={['use', 'fork', 'like']}
      />
    ))}
  </Tab>
</Tabs>
```

---

## Future: Indicator Marketplace

### Premium Indicators

```python
# Create premium (paid) indicator
client.indicators.create_custom_indicator(
    name="PREMIUM_RSI_PRO",
    visibility="public",
    pricing={
        "type": "subscription",  # or "one-time"
        "price": 49.99,
        "currency": "USD",
        "billing_period": "monthly"
    }
)
```

### Indicator Ratings and Reviews

```python
# Rate indicator
client.indicators.rate_indicator(
    indicator_name="COMMUNITY_RSI",
    rating=5,
    review="Best RSI variant I've used!"
)

# Get reviews
reviews = client.indicators.get_reviews(
    indicator_name="COMMUNITY_RSI",
    limit=10
)
```

---

## Security Considerations

### Code Execution Safety

1. **Sandboxed Execution**: Custom indicator code runs in isolated sandbox
2. **Resource Limits**: CPU/memory limits per indicator execution
3. **Restricted Imports**: Only allow safe libraries (pandas, numpy, ta-lib)
4. **Code Review**: Public indicators undergo security audit
5. **Rate Limiting**: Prevent abuse of custom indicator API

### Data Privacy

1. **Private by Default**: New indicators are private
2. **Explicit Sharing**: Users must explicitly share indicators
3. **Audit Trail**: Log all sharing/unsharing actions
4. **Revocable Access**: Creator can revoke access anytime
5. **No Data Leakage**: Shared indicators don't expose user data

---

## Summary

Custom indicators support **three visibility levels**:

| Level | Who Can See | Use Cases | Permissions |
|-------|-------------|-----------|-------------|
| **Private** | Creator only | Proprietary strategies | Full control |
| **Shared** | Creator + users/groups | Team collaboration | Configurable permissions |
| **Public** | Everyone | Community sharing | View/use/fork |

**Key Features**:
- ✅ Three visibility levels (private, shared, public)
- ✅ User and group-based sharing
- ✅ Fine-grained permissions (view, use, edit, fork, reshare)
- ✅ Forking for creating variants
- ✅ Complete audit trail
- ✅ Revocable access
- ✅ Future marketplace support

This design enables secure collaboration while protecting proprietary indicators.
