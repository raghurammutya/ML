# Frontend Integration Documentation

This folder contains comprehensive documentation about how the frontend integrates with backend services and how to add new services like the Alert Service.

## Documents Overview

### 1. FRONTEND_INTEGRATION_GUIDE.md
**Comprehensive Integration Guide** (22 KB)

Complete guide covering:
- Current API client setup with Axios
- Service integration patterns (REST + WebSocket)
- Error handling patterns (service, component, hook level)
- TypeScript type definitions
- How services are used in components
- Step-by-step instructions to integrate Alert Service
- Vite configuration for proxy setup
- Integration checklist

**Best for**: Understanding the full architecture and implementing new services

**Key Sections**:
- API Client Setup
- Service Integration Patterns (Pattern 1-2)
- Error Handling Patterns (3 levels)
- How Services Are Used in Components (2 patterns)
- How to Integrate Alert Service (Steps 1-4)

---

### 2. FRONTEND_INTEGRATION_SUMMARY.md
**Quick Reference Summary** (16 KB)

Fast reference covering:
- Core files analyzed with absolute paths
- Current service integration patterns overview
- Frontend architecture and directory structure
- Technology stack
- How each service currently works (Trading, Labels, FO, Monitor, Replay)
- Alert Service backend structure
- Integration checklist
- Key patterns to follow
- Common issues and solutions
- Testing guide
- Next steps

**Best for**: Quick lookups and understanding existing services

**Key Sections**:
- Quick Reference (3 patterns)
- Directory Structure
- How Each Service Works (5 services detailed)
- Integration Checklist
- Key Patterns
- Testing Guide

---

### 3. FRONTEND_API_LOCATIONS.md
**File Locations & Code References** (16 KB)

Detailed reference with:
- Absolute file paths for all frontend files
- Service layer examples with code
- Type definition locations
- Configuration files
- Component examples
- Backend Alert Service paths
- Key code snippets by pattern (7 patterns)
- Environment variables
- Quick copy-paste service templates

**Best for**: Copy-pasting code, finding exact file locations, specific patterns

**Key Sections**:
- Absolute File Paths (all files listed)
- Key Code Snippets (7 detailed patterns)
- Quick Templates
- Environment Variables

---

## How to Use These Documents

### For Understanding the Architecture
1. Start with **FRONTEND_INTEGRATION_SUMMARY.md** - Get the big picture
2. Read **FRONTEND_INTEGRATION_GUIDE.md** - Deep dive into patterns
3. Reference **FRONTEND_API_LOCATIONS.md** - Find specific files

### For Implementing Alert Service
1. Read **FRONTEND_INTEGRATION_GUIDE.md** sections "How to Integrate Alert Service"
2. Follow the "Integration Checklist"
3. Use code snippets from **FRONTEND_API_LOCATIONS.md** as templates
4. Copy patterns from existing services (trading.ts, labels.ts)

### For Quick Lookups
- File paths → **FRONTEND_API_LOCATIONS.md**
- Service patterns → **FRONTEND_INTEGRATION_SUMMARY.md**
- Code examples → **FRONTEND_API_LOCATIONS.md**
- Error handling → **FRONTEND_INTEGRATION_GUIDE.md**

---

## File Structure

```
Documentation/
├── FRONTEND_INTEGRATION_README.md (this file)
├── FRONTEND_INTEGRATION_GUIDE.md (comprehensive guide)
├── FRONTEND_INTEGRATION_SUMMARY.md (quick reference)
└── FRONTEND_API_LOCATIONS.md (file paths & code)

Frontend Source Code/
├── frontend/src/
│   ├── services/
│   │   ├── api.ts (shared Axios client)
│   │   ├── trading.ts (REST API pattern)
│   │   ├── labels.ts (WebSocket pattern)
│   │   ├── fo.ts (WebSocket pattern)
│   │   ├── monitor.ts (WebSocket pattern)
│   │   ├── replay.ts (WebSocket class pattern)
│   │   └── cprIndicator.ts
│   ├── types/
│   │   ├── types.ts (main types)
│   │   ├── labels.ts (label types)
│   │   └── replay.ts (replay types)
│   ├── components/
│   │   ├── ErrorBoundary.tsx (error handling)
│   │   ├── trading/
│   │   └── nifty-monitor/
│   ├── pages/
│   │   └── MonitorPage.tsx (component example)
│   ├── context/ (to be created for alerts)
│   └── App.tsx
└── vite.config.ts (proxy configuration)
```

---

## Quick Navigation

### By Task

**I want to...**
- Understand the API client → See FRONTEND_API_LOCATIONS.md "Pattern 1"
- Implement a REST service → See FRONTEND_API_LOCATIONS.md "Pattern 2"
- Implement WebSocket → See FRONTEND_API_LOCATIONS.md "Pattern 3"
- Handle errors → See FRONTEND_INTEGRATION_GUIDE.md "Error Handling Patterns"
- Integrate Alert Service → See FRONTEND_INTEGRATION_GUIDE.md "How to Integrate Alert Service"
- Find a specific file → See FRONTEND_API_LOCATIONS.md "Absolute File Paths"
- Copy a component pattern → See FRONTEND_API_LOCATIONS.md "Pattern 6"
- Configure Vite proxy → See FRONTEND_API_LOCATIONS.md "Pattern 7"

### By Service

**Trading Service**
- How it works → FRONTEND_INTEGRATION_SUMMARY.md "1. Trading Service"
- Code example → FRONTEND_API_LOCATIONS.md "Pattern 2"
- File path → /mnt/.../frontend/src/services/trading.ts

**Labels Service**
- How it works → FRONTEND_INTEGRATION_SUMMARY.md "2. Labels Service"
- Code example → FRONTEND_API_LOCATIONS.md "Pattern 3"
- File path → /mnt/.../frontend/src/services/labels.ts

**FO Service**
- How it works → FRONTEND_INTEGRATION_SUMMARY.md "3. FO Service"
- Code example → FRONTEND_API_LOCATIONS.md (see FO endpoints)
- File path → /mnt/.../frontend/src/services/fo.ts

**Monitor Service**
- How it works → FRONTEND_INTEGRATION_SUMMARY.md "4. Monitor Service"
- Code example → See labels.ts pattern (similar WebSocket)
- File path → /mnt/.../frontend/src/services/monitor.ts

**Replay Service**
- How it works → FRONTEND_INTEGRATION_SUMMARY.md "5. Replay Service"
- Code example → FRONTEND_API_LOCATIONS.md "Pattern 4"
- File path → /mnt/.../frontend/src/services/replay.ts

**Alert Service (to implement)**
- Integration guide → FRONTEND_INTEGRATION_GUIDE.md "Step 1-4"
- Template → FRONTEND_INTEGRATION_GUIDE.md "Step 1: Create Alert Service"
- Checklist → FRONTEND_INTEGRATION_SUMMARY.md "Integration Checklist"

---

## Key Takeaways

### Architecture Principles
1. **Centralized API Client**: All HTTP requests use shared `api` instance
2. **Service Layer Pattern**: Each backend endpoint gets a service file
3. **Type Safety**: All responses have TypeScript interfaces
4. **Error Resilience**: Services return defaults, don't throw for non-critical errors
5. **Real-time Support**: WebSocket utilities follow consistent patterns
6. **Environment Config**: Base URLs from environment variables

### Integration Patterns
1. **HTTP Pattern**: GET/POST/PATCH/DELETE → api client → return Promise
2. **WebSocket Pattern**: buildUrl() → connectStream() → subscribe/parse
3. **Component Pattern**: useEffect + useState + service calls
4. **Context Pattern**: Provider wraps component tree, useContext in components
5. **Error Pattern**: try-catch at service level, ErrorBoundary at component level

### Best Practices
- Always import from shared `api` client
- Define TypeScript interfaces before functions
- Validate response structure before using
- Log errors, return sensible defaults
- Test WebSocket with browser console
- Configure proxy in vite.config.ts before using
- Use environment variables for configuration

---

## Implementation Order (Alert Service)

1. **Create Service** → Copy trading.ts pattern, update endpoints to /alerts
2. **Create Types** → Add to types.ts or create types/alerts.ts
3. **Create Context** → Follow labels pattern with WebSocket subscription
4. **Create Components** → Panel for list, form for create/edit
5. **Update Vite Config** → Add /alerts proxy
6. **Integrate** → Wrap app with AlertProvider
7. **Test** → Manual testing with curl and browser console
8. **Deploy** → Verify all proxies working

---

## Technology Stack Reference

- **HTTP**: Axios 1.6.2
- **Real-time**: Native WebSocket API
- **UI**: React 18.2.0
- **Language**: TypeScript 5.3.2
- **Build**: Vite 5.0.4
- **Styling**: CSS (no framework detected)
- **Charts**: lightweight-charts 4.2.3

---

## Common Commands

### Development
```bash
cd frontend
npm install
npm run dev          # Start dev server on port 3002
npm run build        # Build for production
npm run preview      # Preview production build
```

### Testing Services
```bash
# Test API endpoint
curl http://localhost:3002/health

# Test WebSocket
wscat -c ws://localhost:3002/alerts/stream

# Browser console
const ws = new WebSocket('ws://localhost:3002/alerts/stream')
ws.onmessage = (e) => console.log(JSON.parse(e.data))
```

---

## Troubleshooting

### WebSocket Connection Refused
- Check vite.config.ts proxy configuration
- Verify backend service is running on correct port
- Check ws: true is set in proxy config

### API 404 Errors
- Verify API_BASE constant matches backend endpoint
- Check proxy target in vite.config.ts
- Test direct backend endpoint with curl

### Type Errors
- Ensure interfaces match actual API response
- Check export statement in service file
- Verify type imports in components

### CORS Errors
- Check backend has CORS enabled
- Verify changeOrigin: true in proxy config
- Check allowed origins in backend settings

---

## Additional Resources

- Axios docs: https://axios-http.com/
- WebSocket MDN: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
- React docs: https://react.dev/
- TypeScript docs: https://www.typescriptlang.org/
- Vite docs: https://vitejs.dev/

---

## Questions?

Refer to:
1. The specific document for your task (see "By Task" section)
2. The code example from existing services
3. The pattern template in FRONTEND_API_LOCATIONS.md

All files are in the same directory as this README.

