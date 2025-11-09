# User Service - Sprint Plan

**Generated:** 2025-11-09
**Total Sprints:** 5
**Estimated Duration:** 7-8 weeks

---

## Sprint Priorities

### Sprint 1: API Keys (Week 1) - HIGHEST PRIORITY
**Goal:** Enable SDK users to authenticate with API keys instead of username/password

**Tasks:**
1. Database schema for API keys
2. API key generation and management endpoints
3. Authentication middleware for API keys
4. Scope enforcement
5. Rate limiting by API key
6. Testing and documentation

**Deliverables:**
- `POST /v1/api-keys` - Generate API key
- `GET /v1/api-keys` - List user's API keys
- `DELETE /v1/api-keys/{key_id}` - Revoke API key
- `PUT /v1/api-keys/{key_id}` - Update API key
- `POST /v1/api-keys/{key_id}/rotate` - Rotate API key
- API key authentication middleware
- Integration tests
- SDK compatibility tests

---

### Sprint 2: Organizations (Weeks 2-3) - HIGH PRIORITY
**Goal:** Support investment firms with multiple users managing shared trading accounts

**Tasks:**
1. Database schema for organizations
2. Organization CRUD endpoints
3. Organization membership management
4. Organization-level trading accounts
5. Organization-level permissions
6. Organization roles and authorization
7. Testing and documentation

**Deliverables:**
- `POST /v1/organizations` - Create organization
- `GET /v1/organizations/{org_id}` - Get organization
- `PUT /v1/organizations/{org_id}` - Update organization
- `DELETE /v1/organizations/{org_id}` - Delete organization
- `POST /v1/organizations/{org_id}/members` - Add member
- `DELETE /v1/organizations/{org_id}/members/{user_id}` - Remove member
- `GET /v1/organizations/{org_id}/members` - List members
- `POST /v1/organizations/{org_id}/members/{user_id}/roles` - Assign role
- `GET /v1/organizations/{org_id}/trading-accounts` - List org accounts
- Organization authorization policies
- Integration tests

---

### Sprint 3: Families (Weeks 4-5) - HIGH PRIORITY
**Goal:** Support family offices with cross-account permissions and consolidated views

**Tasks:**
1. Database schema for families
2. Family CRUD endpoints
3. Family membership management
4. Cross-account permissions within families
5. Consolidated family portfolio endpoints
6. Family-level settings (risk limits, etc.)
7. Testing and documentation

**Deliverables:**
- `POST /v1/families` - Create family
- `GET /v1/families/{family_id}` - Get family
- `PUT /v1/families/{family_id}` - Update family
- `DELETE /v1/families/{family_id}` - Delete family
- `POST /v1/families/{family_id}/members` - Add member
- `DELETE /v1/families/{family_id}/members/{user_id}` - Remove member
- `GET /v1/families/{family_id}/members` - List members
- `GET /v1/families/{family_id}/accounts` - List family accounts
- `GET /v1/families/{family_id}/portfolio` - Consolidated portfolio
- Family authorization policies
- Integration tests

---

### Sprint 4: Email Verification & Invitations (Week 6) - MEDIUM PRIORITY
**Goal:** Verify email ownership and enable user invitations to orgs/families

**Tasks:**
1. Email service integration (SendGrid/SES)
2. Email verification flow
3. Invitation system for organizations
4. Invitation system for families
5. Email templates
6. Testing and documentation

**Deliverables:**
- `POST /v1/auth/email/verify` - Verify email with token
- `POST /v1/auth/email/resend-verification` - Resend verification
- `POST /v1/organizations/{org_id}/invite` - Invite to org
- `POST /v1/families/{family_id}/invite` - Invite to family
- `POST /v1/invitations/{token}/accept` - Accept invitation
- `GET /v1/invitations/pending` - List pending invitations
- Email templates (verification, invitation)
- Integration tests

---

### Sprint 5: Admin Dashboard & Enhancements (Week 7-8) - LOW PRIORITY
**Goal:** Admin capabilities and additional authentication methods

**Tasks:**
1. Admin user management endpoints
2. Admin organization management
3. Admin audit log viewer
4. System health metrics
5. Optional: Additional OAuth providers (GitHub, Microsoft)
6. Optional: Phone/SMS verification
7. Testing and documentation

**Deliverables:**
- `GET /v1/admin/users` - List/search users
- `PUT /v1/admin/users/{user_id}/suspend` - Suspend user
- `PUT /v1/admin/users/{user_id}/activate` - Activate user
- `DELETE /v1/admin/users/{user_id}` - Delete user
- `GET /v1/admin/organizations` - List organizations
- `GET /v1/admin/audit` - Enhanced audit viewer
- `GET /v1/admin/metrics` - System metrics
- Integration tests

---

## Execution Strategy

### For Each Sprint:

1. **Create detailed prompt file** in `docs/sprints/sprint-N-[name].md`
2. **Execute prompt** with Claude CLI
3. **Run tests** (unit + integration)
4. **Manual testing** with SDK and API calls
5. **Documentation** update
6. **Git commit** with descriptive message
7. **Push to GitHub** at logical milestones

### Testing Requirements:

- Unit tests for all services
- Integration tests for all endpoints
- SDK compatibility tests
- Manual API testing with curl/httpie
- Database migration testing (up and down)

### Git Strategy:

- Feature branches: `feature/sprint-1-api-keys`, `feature/sprint-2-organizations`, etc.
- Commit after each logical unit (e.g., "Add API key database schema")
- Push after each sprint completion
- Create PR for review (if applicable)

---

## Dependencies Between Sprints

- **Sprint 1** (API Keys) - Independent, can start immediately
- **Sprint 2** (Organizations) - Depends on Sprint 1 for org-level API keys (optional)
- **Sprint 3** (Families) - Independent of Sprint 2
- **Sprint 4** (Email/Invitations) - Depends on Sprint 2 & 3 for org/family invitations
- **Sprint 5** (Admin) - Depends on Sprint 2 & 3 for org/family management

---

## Risk Mitigation

1. **Database Migrations:** Test rollback for each migration
2. **Backward Compatibility:** Ensure existing endpoints continue to work
3. **Performance:** Load test authorization with new org/family policies
4. **Security:** Audit all new endpoints for vulnerabilities
5. **SDK Compatibility:** Test SDK with all new authentication methods

---

## Success Criteria

### Sprint 1 (API Keys):
- ✅ SDK can authenticate with API keys
- ✅ API keys can be generated, listed, revoked, rotated
- ✅ Scope enforcement works correctly
- ✅ Rate limiting per API key works

### Sprint 2 (Organizations):
- ✅ Investment firms can create organizations
- ✅ Multiple users can join organizations
- ✅ Org-level trading accounts work
- ✅ Org-level permissions enforced correctly

### Sprint 3 (Families):
- ✅ Families can be created
- ✅ Family members can share accounts
- ✅ Consolidated family portfolio view works
- ✅ Family-level permissions enforced correctly

### Sprint 4 (Email/Invitations):
- ✅ Email verification flow works end-to-end
- ✅ Users can invite others to orgs/families
- ✅ Invitation acceptance works correctly

### Sprint 5 (Admin):
- ✅ Admins can manage all users and orgs
- ✅ Audit logs are easily queryable
- ✅ System metrics are accurate

---

**Next Steps:**
1. Review sprint plan with stakeholders
2. Create detailed prompts for Sprint 1
3. Begin Sprint 1 execution
