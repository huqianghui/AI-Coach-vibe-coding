# Roadmap: AI Coach Platform (BeiGene)

## Overview

This roadmap delivers the AI Coach Platform in 6 phases: foundation and architecture first, then F2F text coaching (the core value loop), scoring & assessment enhancements, dashboards & reporting, training material management, and conference presentation module. Each phase builds on the previous one and delivers a coherent, demonstrable capability. Architecture-first principle applies throughout -- pluggable adapters, config-driven features, and shared components are established in Phase 01 and extended by every subsequent phase.

## Phases

**Phase Numbering:**
- Zero-padded phases (01, 02, 03): Planned milestone work
- Decimal phases (01.1, 02.1): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 01: Foundation, Auth, and Design System** - Pluggable architecture, authentication, shared UI components, i18n, and responsive app shell
- [x] **Phase 02: F2F Text Coaching and Scoring** - HCP/scenario configuration, text-based coaching simulation, multi-dimensional scoring, and feedback
- [x] **Phase 03: Scoring & Assessment** - Real-time coaching suggestions, post-session reports, customizable scoring rubrics
- [x] **Phase 04: Dashboard & Reporting** - Personal dashboard, group analytics, export (PDF/Excel), training progress tracking
- [x] **Phase 05: Training Material Management** - Document upload, versioning, retention policies, AI knowledge base integration
- [x] **Phase 06: Conference Presentation Module** - One-to-many simulation, live transcription, audience Q&A, presentation scoring (completed 2026-03-25)
- [x] **Phase 07: Azure Service Integration** - Admin Azure config persistence, real connection testing, dynamic provider switching (mock → Azure OpenAI/Speech/Avatar) (completed 2026-03-27)
- [x] **Phase 08: Voice & Avatar Demo Integration** - Integrate Azure Voice Live Agent with Avatar into the AI Coach platform for real-time voice coaching with digital HCP avatar (completed 2026-03-28)
- [x] **Phase 09: Integration Testing with Real Azure Services** - Unified AI Foundry config, 7 interaction modes, agent mode runtime, integration tests, E2E demo validation (completed 2026-03-29)
- [x] **Phase 10: UI Polish & Professional Unification** - Comprehensive UI overhaul for professional appearance, unified design language, polished visuals for BeiGene customer demo (completed 2026-03-29)
- [x] **Phase 11: HCP Profile Agent Integration** - Auto-create AI Foundry agent when adding HCP profiles, bidirectional sync, table UI redesign (completed 2026-03-31)
- [x] **Phase 12: Voice Realtime API & Agent Mode Integration** - Per-HCP digital persona (voice/avatar/conversation config), auto-mode selection, fallback chain, tabbed HCP editor (completed 2026-04-02)
- [x] **Phase 13: Voice Live Instance & Agent Voice Management** - Create/manage Voice Live instances, bind to HCP Agents, enable Voice mode, configure speech/avatar — matching AI Foundry portal workflow (completed 2026-04-08)
- [x] **Phase 14: HCP Agent Refactor** - VL Instance read-only reference in HCP editor, VL Management rewrite with rich CRUD, Knowledge/Tools placeholder tabs (completed 2026-04-08)
- [x] **Phase 15: HCP Editor Agent Config Center** - 重构 HCP 编辑器为 Agent 配置中心：移除空 Knowledge/Tools tab，Voice & Avatar tab 升级为 Model Deployment + Instructions + Playground 预览布局，对齐 Azure AI Foundry Agent 编辑体验 (completed 2026-04-07)
- [x] **Phase 16: Voice Live Refactor — Modularize, Agent Mode, Sync** - 前端 Voice Live 模块化复用，后端 WebSocket 双模式（Model+Agent），SDK 升级 1.2.0b5，HCP voice 配置同步到 AI Foundry Agent (completed 2026-04-10)
- [x] **Phase 17: Agent Knowledge Base — Foundry IQ Integration** - HCP Agent 知识库管理：连接 Azure AI Search / Foundry IQ，上传训练材料自动创建知识库索引，知识库配置同步到 AI Foundry Agent (completed 2026-04-10)
- [x] **Phase 18: Training Material Download & Preview** - 培训材料文件下载和在线预览：后端添加文件下载 API，前端 PDF 在线预览、DOCX/XLSX 下载，修复 storage_url 信息泄露 (completed 2026-04-10)
- [x] **Phase 21: Scoring Criteria Refactor** - 评分标准模块重构，消除硬编码维度，ScoringRubric 升级为评分唯一权威来源，支持动态自定义维度 (completed 2026-04-28)
- [x] **Phase 27: Prompt Optimizer & Unified Prompt Management** - Integrate prompt-optimizer (Docker sidecar + MCP client), unify all 9 prompts into a versioned registry with optimization history, provide an admin management UI, support creating new prompts, and view historical version content (completed 2026-07-01)

## Phase Details

### Phase 01: Foundation, Auth, and Design System
**Goal**: A running application with login, responsive layout shell, shared component library, i18n framework, and pluggable architecture for all AI services -- the scaffold everything else builds on
**Depends on**: Nothing (first phase)
**Requirements**: ARCH-01, ARCH-02, ARCH-03, ARCH-04, ARCH-05, AUTH-01, AUTH-02, AUTH-03, AUTH-04, UI-01, UI-02, UI-07, PLAT-01, PLAT-02, PLAT-04, PLAT-05
**Success Criteria** (what must be TRUE):
  1. User can log in with username/password and see a responsive app shell with sidebar navigation -- session persists across browser refresh
  2. Admin and User roles exist -- admin sees admin routes, user does not
  3. All UI text is externalized via react-i18next and the app can switch between zh-CN and en-US
  4. AI service adapters (LLM, STT, TTS, Avatar) use pluggable provider pattern -- a mock provider works end-to-end without any Azure credentials
  5. Feature toggles, Azure service endpoints, voice mode selection, and region configuration are driven by config (not hardcoded) -- changing config changes behavior without code changes
**Plans**: 5 plans

Plans:
- [x] 01-01-PLAN.md -- Backend JWT auth: User model, login/me endpoints, role-based access, seed data
- [x] 01-02-PLAN.md -- Design tokens + UI component library: Figma Make theme adaptation, 17 shadcn/ui components
- [x] 01-03-PLAN.md -- Pluggable AI adapters + config: STT/TTS/Avatar base+mock, ServiceRegistry, feature toggles, config API
- [x] 01-04-PLAN.md -- Frontend shell: React bootstrap, i18n, login page, user/admin layouts, router with auth guards
- [x] 01-05-PLAN.md -- Integration wiring: auto-register adapters, config context, integration tests, full verification

**UI hint**: yes

### Phase 01.1: UI Figma Alignment (INSERTED)

**Goal:** Align existing frontend with 5 Figma Make generated screens -- login polish, full user dashboard, scenario selection page, F2F training session page, and 11 new shared domain components. All pages use i18n, design tokens, and mock data (backend integration deferred to Phase 2).
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05
**Depends on:** Phase 1
**Plans:** 4/6 plans executed

Plans:
- [x] 01.1-01-PLAN.md -- Install Radix deps, 4 new UI base components (ScrollArea, Tabs, Progress, Textarea), i18n namespaces
- [x] 01.1-02-PLAN.md -- Login page polish: SVG logo, card shadow, auth layout gradient/language switcher/copyright
- [x] 01.1-03-PLAN.md -- 11 shared domain components: StatCard, SessionItem, ActionCard, HCPProfileCard, ChatBubble, ChatInput, etc.
- [x] 01.1-04-PLAN.md -- User dashboard page + scenario selection page + route registration
- [x] 01.1-05-PLAN.md -- F2F training session: 3 coach panels + full-screen training page + route registration
- [x] 01.1-06-PLAN.md -- Build validation + visual verification checkpoint

### Phase 02: F2F Text Coaching and Scoring
**Goal**: An MR can select a scenario, have a text-based F2F conversation with an AI HCP that behaves according to its profile, and receive a multi-dimensional scored feedback report after the session
**Depends on**: Phase 01
**Requirements**: HCP-01, HCP-02, HCP-03, HCP-04, HCP-05, COACH-01, COACH-02, COACH-03, COACH-08, COACH-09, SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05, UI-03, UI-05, PLAT-03
**Success Criteria** (what must be TRUE):
  1. Admin can create HCP profiles (personality, specialty, objections, communication style) and training scenarios (product, key messages, difficulty, scoring weights) from the web UI
  2. User can browse and select a training scenario, then start a text-based F2F coaching session with the assigned AI HCP
  3. AI HCP responds in character (personality, knowledge, objections) based on its profile -- conversation feels realistic and contextual
  4. During the session, a side panel shows real-time key message delivery checklist and coaching hints
  5. After session completion, user sees a multi-dimensional scoring report with per-dimension scores, strengths/weaknesses with conversation quotes, and actionable improvement suggestions
**Plans**: 8 plans

Plans:
- [x] 02-01-PLAN.md -- Backend data models, Pydantic schemas, Alembic migration, sse-starlette dependency
- [x] 02-02-PLAN.md -- Frontend TypeScript types, i18n namespaces (coach/admin/scoring), Slider component, recharts install
- [x] 02-03-PLAN.md -- Backend HCP profile + scenario CRUD API routers, service layer, seed data
- [x] 02-04-PLAN.md -- Backend session lifecycle + SSE streaming chat + scoring service + enhanced mock adapter
- [x] 02-05-PLAN.md -- Frontend API client modules + TanStack Query hooks + SSE streaming hook
- [x] 02-06-PLAN.md -- Admin pages: HCP profile management, scenario management, Azure config
- [x] 02-07-PLAN.md -- User pages: scenario selection, F2F coaching session with live chat, scoring feedback with radar chart
- [x] 02-08-PLAN.md -- Integration wiring: router, admin sidebar, Azure config API, full flow verification

**UI hint**: yes

### Phase 03: Scoring & Assessment
**Goal**: Complete the scoring system with real-time coaching suggestions during sessions, detailed post-session reports with strengths/weaknesses/improvement areas, and admin-customizable scoring criteria/rubrics
**Depends on**: Phase 02
**Requirements**: SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05, COACH-08, COACH-09
**Success Criteria** (what must be TRUE):
  1. During a coaching session, the system provides real-time suggestions and coaching tips in the side panel based on conversation context
  2. After session completion, user sees a detailed post-session report with strengths, weaknesses, conversation quotes, and actionable improvement areas
  3. Admin can configure customizable scoring rubrics -- defining dimensions, weights, and criteria per scenario type
  4. Scoring results are persisted and queryable for historical trend analysis
  5. All new code has unit tests with >=95% coverage maintained
**Plans**: 4 plans

Plans:
- [x] 03-01-PLAN.md -- Backend services: rubric CRUD, scoring rubric integration, SSE suggestion wiring, report/suggestions/history endpoints, tests
- [x] 03-02-PLAN.md -- Frontend data layer: TypeScript types, API clients, TanStack Query hooks for rubrics/reports/history
- [x] 03-03-PLAN.md -- Frontend pages: admin rubric management, enhanced scoring feedback with full report + PDF, session history
- [x] 03-04-PLAN.md -- Integration wiring: router registration, sidebar nav, seed default rubric, full flow verification

**UI hint**: yes

### Phase 04: Dashboard & Reporting
**Goal**: MRs can track their improvement over time via a personal dashboard, and admins can view organization-level analytics with export capabilities
**Depends on**: Phase 03
**Requirements**: UI-04, UI-06, ANLYT-01, ANLYT-02, ANLYT-03, ANLYT-04, ANLYT-05
**Success Criteria** (what must be TRUE):
  1. User can view a personal dashboard with score overview, recent sessions, and a skill radar chart showing multi-dimensional performance
  2. User can view session history (date, scenario, score, duration) and personal performance trends over time per scoring dimension
  3. Admin can view organization-level analytics including BU comparisons, skill gap heatmaps, and training completion rates
  4. Reports can be exported as PDF/Excel for offline review
  5. All new code has unit tests with >=95% coverage maintained
**Plans**: 6 plans

Plans:
- [x] 04-01-PLAN.md -- Backend foundation: Alembic migration (business_unit), analytics schemas, analytics service, export service, recommendation engine
- [x] 04-02-PLAN.md -- Frontend data layer: TypeScript types, API client, TanStack Query hooks, i18n analytics namespace, file-saver install
- [x] 04-03-PLAN.md -- Backend API: analytics router with 7 endpoints, main.py registration, seed data with BU values
- [x] 04-04-PLAN.md -- Frontend user pages: enhanced dashboard with live stats, session history with skill radar, chart components
- [x] 04-05-PLAN.md -- Frontend admin pages: org analytics dashboard, reports page, BU bar chart, skill gap heatmap, route registration, backend tests
- [x] 04-06-PLAN.md -- Gap closure: seed session data, wire reports pages to live data, date range filtering, PDF print export

**UI hint**: yes

### Phase 05: Training Material Management
**Goal**: Admin can upload, version, and manage training materials (Word/Excel/PDF) organized by product -- materials feed into AI knowledge base for more accurate HCP simulation
**Depends on**: Phase 02
**Requirements**: CONTENT-01, CONTENT-02, CONTENT-03
**Success Criteria** (what must be TRUE):
  1. Admin can upload training documents (Word, Excel, PDF) organized by product via the web UI
  2. Uploaded materials support versioning and archiving -- admin can see version history and restore previous versions
  3. Retention policies enable auto-deletion of expired materials per configurable rules
  4. Uploaded materials are indexed and available to the AI knowledge base for enhanced HCP simulation accuracy
  5. All new code has unit tests with >=95% coverage maintained
**Plans**: 3 plans

Plans:
- [x] 05-01-PLAN.md -- Backend foundation: ORM models, Pydantic schemas, storage adapter, text extractor, Alembic migration, new dependencies
- [x] 05-02-PLAN.md -- Backend API: material service, REST router, prompt builder RAG integration, comprehensive tests
- [x] 05-03-PLAN.md -- Frontend: TypeScript types, API client, TanStack Query hooks, admin page with drag-and-drop upload, i18n, route registration

**UI hint**: yes

### Phase 06: Conference Presentation Module
**Goal**: MRs can practice conference presentations to multiple virtual HCP audience members with turn management, live transcription, Q&A, and multi-scenario scoring
**Depends on**: Phase 02
**Requirements**: CONF-01, CONF-02, CONF-03, CONF-04, COACH-04, COACH-05, COACH-06, COACH-07
**Success Criteria** (what must be TRUE):
  1. User can start a conference presentation session with multiple virtual HCP audience members (one-to-many simulation)
  2. Live transcription displays audio-to-text on screen during the presentation
  3. Virtual HCP audience members ask contextual questions with turn management
  4. Conference presentations are scored using the multi-dimensional scoring system with presentation-specific criteria
  5. All new code has unit tests with >=95% coverage maintained
**Plans**: 6 plans

Plans:
- [x] 06-01-PLAN.md -- Backend foundation: ConferenceAudienceHcp model, session/message extensions, Alembic migration, schemas, TurnManager, voice dependency
- [x] 06-02-PLAN.md -- Frontend data layer: TypeScript types, API client, TanStack Query hooks, multi-speaker SSE hook, i18n conference namespace
- [x] 06-03-PLAN.md -- Backend services + API: conference_service, conference router with SSE, prompt builder extension, Azure STT/TTS adapters
- [x] 06-04-PLAN.md -- Frontend components + page: 11 conference components, extended ChatBubble, full-screen conference session page
- [x] 06-05-PLAN.md -- Integration wiring: route registration, navigation, seed data, admin audience config, full-flow verification
- [x] 06-06-PLAN.md -- Comprehensive backend tests: TurnManager, conference service, API integration, STT/TTS adapters, schemas, models (>=95% coverage)

**UI hint**: yes

### Phase 07: Azure Service Integration
**Goal**: Admin Azure config persistence, real connection testing, dynamic provider switching (mock to Azure OpenAI/Speech/Avatar)
**Depends on**: Phase 01
**Requirements**: PLAT-03, ARCH-05
**Success Criteria** (what must be TRUE):
  1. Admin can configure Azure service endpoints and API keys via admin UI
  2. API keys are stored encrypted (Fernet) in the database
  3. Connection testing validates Azure service reachability
  4. Dynamic provider switching allows runtime change from mock to Azure providers
  5. All new code has unit tests with >=95% coverage maintained
**Plans**: 4 plans

Plans:
- [x] 07-01-PLAN.md -- Config data foundation: ServiceConfig model, Fernet encryption, config service, schemas, migration
- [x] 07-02-PLAN.md -- Admin config API routes and frontend config page
- [x] 07-03-PLAN.md -- Connection testing and Azure service validation
- [x] 07-04-PLAN.md -- Dynamic provider switching and runtime reconfiguration

**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 01 -> 01.1 -> 02 -> 03 -> 04 -> 05 -> 06 -> 07 -> 08 -> 09 -> 10 -> 11 -> 12 -> 13 -> 14 -> 15 -> 16 -> 17 -> 18 (all complete) -> 19 (next) -> 20

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 01. Foundation, Auth, and Design System | 5/5 | Complete | - |
| 01.1. UI Figma Alignment | 6/6 | Complete | - |
| 02. F2F Text Coaching and Scoring | 8/8 | Complete | - |
| 03. Scoring & Assessment | 4/4 | Complete | - |
| 04. Dashboard & Reporting | 6/6 | Complete | - |
| 05. Training Material Management | 3/3 | Complete | - |
| 06. Conference Presentation Module | 6/6 | Complete | 2026-03-25 |
| 07. Azure Service Integration | 4/4 | Complete    | 2026-03-27 |
| 08. Voice & Avatar Demo Integration | 5/4 | Complete   | 2026-03-28 |
| 09. Integration Testing with Real Azure Services | 5/5 | Complete    | 2026-03-29 |
| 10. UI Polish & Professional Unification | 6/6 | Complete    | 2026-03-29 |
| 11. HCP Profile Agent Integration | 3/3 | Complete    | 2026-03-31 |
| 12. Voice Realtime API & Agent Mode Integration | 4/4 | Complete    | 2026-04-02 |
| 13. Voice Live Instance & Agent Voice Management | 3/3 | Complete   | 2026-04-08 |
| 14. HCP Agent Refactor | 4/4 | Complete   | 2026-04-08 |
| 15. HCP Editor Agent Config Center | 3/3 | Complete   | 2026-04-07 |
| 16. Voice Live Refactor — Modularize, Agent Mode, Sync | 4/4 | Complete   | 2026-04-10 |
| 17. Agent Knowledge Base — Foundry IQ Integration | 3/3 | Complete   | 2026-04-10 |
| 18. Training Material Download & Preview | 3/3 | Complete | 2026-04-10 |
| 19. AI Coach Skill Module | 6/8 | In Progress|  |
| 20. Skill Dry Run Simulation | 5/5 | Complete   | 2026-04-26 |

### Phase 16: Voice Live Refactor — Modularize, Agent Mode, Sync

**Goal:** 前端 Voice Live 功能模块化（提取共享 utils/hooks/components 消除重复），后端 WebSocket proxy 支持双模式（Model + Agent），SDK 升级到 1.2.0b5，HCP 绑定的 voice/avatar 配置完整同步到 AI Foundry Agent（解决 portal 中 agent voice 配置为空的问题）。
**Requirements**: VL-16-01, VL-16-02, VL-16-03, VL-16-04, VL-16-05, VL-16-06
**Depends on:** Phase 15
**Plans:** 4/4 plans executed

**Success Criteria** (what must be TRUE):
  1. 前端 Voice Live 重复代码提取为共享模块（voice-utils、useVoiceSessionLifecycle、AssignHcpDialog、voice-constants）
  2. VL Instance Editor 使用 Model 模式连接 Voice Live 并可进行联通测试
  3. HCP 页面 Playground 使用 Agent 模式调用 Voice Live（前提：HCP 已同步且有 agent-id）
  4. Agent 模式连接失败时返回错误（不做 silent fallback）— owner decision overrides original fallback design
  5. HCP 绑定的 VoiceLiveInstance 配置（含 avatar）完整同步到 AI Foundry Agent metadata
  6. VL Instance 更新/分配/取消分配时触发关联 HCP agent 重新同步
  7. 前后端测试覆盖 + TypeScript/Ruff 构建通过

Plans:
- [x] 16-01-PLAN.md -- Frontend Voice Live modularization: extract voice-utils, useVoiceSessionLifecycle, AssignHcpDialog, voice-constants
- [x] 16-02-PLAN.md -- Backend dual-mode WebSocket (Model+Agent), SDK 1.2.0b5 upgrade, agent pre-check, NO fallback
- [x] 16-03-PLAN.md -- Voice Live config sync to AI Foundry Agent: fix build_voice_live_metadata, avatar fields, re-sync triggers, agent versioning, clear-on-unassign
- [x] 16-04-PLAN.md -- ROADMAP fix (no-fallback), frontend tests, build verification, human visual checkpoint

**UI hint**: yes

### Phase 07: Azure Service Integration

**Goal**: Admin can configure Azure OpenAI, Speech, and Avatar through the web UI with real connection testing, configurations persist to the database, and the coaching system dynamically switches from mock to real Azure providers based on admin settings
**Depends on**: Phase 02
**Requirements**: PLAT-03, ARCH-05, PLAT-05
**Success Criteria** (what must be TRUE):
  1. Admin can configure Azure OpenAI endpoint/key/model/region from the Azure Config page and the settings persist across server restarts (stored in database)
  2. Admin can configure Azure Speech (STT/TTS) and Azure Avatar settings from the same page
  3. "Test Connection" button actually validates connectivity to the configured Azure service and shows real success/failure status
  4. When Azure OpenAI is configured and tested, F2F coaching sessions use the real Azure OpenAI model instead of mock responses
  5. When Azure Speech is configured, voice mode becomes available for coaching sessions (STT for input, TTS for HCP responses)
  6. The system gracefully falls back to mock adapters when Azure services are not configured or unavailable
**Plans**: 4 plans

Plans:
- [x] 07-01-PLAN.md -- Backend foundation: ServiceConfig model, Fernet encryption, schemas, Alembic migration, config service
- [x] 07-02-PLAN.md -- AzureOpenAIAdapter: streaming LLM adapter with conversation history, unit tests
- [x] 07-03-PLAN.md -- Backend API + dynamic switching: PUT/test/GET endpoints, connection tester, lifespan DB loading, session history wiring
- [ ] 07-04-PLAN.md -- Frontend wiring: TypeScript types, API client, TanStack Query hooks, wire azure-config page to real API

**UI hint**: yes

### Phase 08: Voice & Avatar Demo Integration
**Goal**: Integrate the existing Voice-Live-Agent-With-Avatar demo (Azure Voice Live API + Avatar) into the AI Coach platform, enabling real-time voice-based coaching sessions where MRs talk to a digital HCP avatar with natural speech interaction
**Depends on**: Phase 07
**Requirements**: COACH-04, COACH-05, COACH-07, EXT-04, PLAT-05
**Success Criteria** (what must be TRUE):
  1. User can start a voice-enabled coaching session that uses Azure Voice Live API for real-time speech interaction with the AI HCP
  2. Azure AI Avatar renders a digital human visual for the HCP during voice coaching sessions
  3. Voice interaction is integrated with the existing coaching session lifecycle (start -> in_progress -> completed -> scored)
  4. The system gracefully falls back to text-only or TTS-only mode when Avatar/Voice Live services are unavailable
  5. Admin can configure Voice Live and Avatar settings from the Azure Config page
  6. All new code has unit tests with >=95% coverage maintained
**Plans**: 4 plans

Plans:
- [x] 08-01-PLAN.md -- Backend foundation: Alembic migration (session mode), voice_live schemas/service, token broker API, connection tester, tests
- [x] 08-02-PLAN.md -- Frontend data layer: TypeScript types, i18n voice namespace, API client, TanStack Query hooks, audio-processor.js, tests
- [x] 08-03-PLAN.md -- Voice hooks + leaf components: useVoiceLive, useAvatarStream, useAudioHandler, 7 voice UI components, component tests
- [x] 08-04-PLAN.md -- Container components + wiring: VoiceSession container, route registration, admin config Voice Live card, transcript flush, tests

**UI hint**: yes

### Phase 09: Integration Testing with Real Azure Services
**Goal**: Implement unified AI Foundry config (replacing 8 separate ServiceConfig rows), expand to 7 interaction modes, wire agent mode runtime end-to-end, redesign admin UI with single AI Foundry card, then validate all Azure service integrations with real credentials and polish demo experience for BeiGene customer presentations
**Depends on**: Phase 08
**Requirements**: COACH-04, COACH-05, COACH-06, COACH-07, PLAT-03, PLAT-05
**Success Criteria** (what must be TRUE):
  1. Admin configures a single AI Foundry endpoint/region/API key — all 7 services derive from this unified config
  2. Platform supports all 7 interaction modes (Text, Voice Pipeline, Digital Human Speech+Model, Voice Realtime Model, Digital Human Realtime Model, Voice Realtime Agent, Digital Human Realtime Agent)
  3. Agent mode works end-to-end: token broker returns agent_id/project_name, frontend connects via voice-agent/realtime WebSocket
  4. Two-level mode selector UI: communication type first (Text/Voice/Digital Human), then engine (Pipeline/Realtime Model/Realtime Agent)
  5. Integration tests validate each Azure service with real credentials (pytest --run-integration)
  6. E2E demo flow works: Login → Admin AI Foundry config → Text session → Voice session → Avatar session → Score report
**Plans**: 5 plans

Plans:
- [x] 09-01-PLAN.md -- Backend unified AI Foundry config, 7-mode session schema, agent mode token broker
- [x] 09-02-PLAN.md -- Frontend types, AI Foundry admin page redesign, two-level mode selector types
- [x] 09-03-PLAN.md -- Two-level mode selector component, agent mode WebSocket wiring in use-voice-live
- [x] 09-04-PLAN.md -- Backend pytest integration tests (Azure OpenAI, Speech, Voice Live, Avatar)
- [x] 09-05-PLAN.md -- Playwright E2E demo-flow test, pre-demo smoke test checklist

**UI hint**: yes

### Phase 10: UI Polish & Professional Unification

**Goal:** Comprehensive UI overhaul for professional appearance and consistency across all pages — unified design language, accent color theme picker, page transitions, navigation polish, Figma-audited spacing/typography, and demo-ready seed data for BeiGene customer presentations
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07
**Depends on:** Phase 09
**Plans:** 6/6 plans complete

Plans:
- [x] 10-01-PLAN.md -- Theme system foundation: 5 accent color CSS themes, theme store, flash prevention, splash screen, page transition keyframes
- [x] 10-02-PLAN.md -- Navigation polish: ThemePicker, Breadcrumb, PageTransition components, grouped admin sidebar, active nav states, layout dark mode
- [x] 10-03-PLAN.md -- Shared component audit: design token consistency, icon sizing, Badge success variant, Sonner theming, 404 page
- [x] 10-04-PLAN.md -- User page audit: login, dashboard, training, session history, scoring, reports, training sessions vs Figma specs
- [x] 10-05-PLAN.md -- Admin page audit: dashboard, users, HCP profiles, scenarios, rubrics, materials, reports, azure config, settings vs Figma specs
- [x] 10-06-PLAN.md -- Demo seed data polish: BeiGene products, bilingual HCPs, final build verification

### Phase 11: HCP Profile Agent Integration — Auto-create AI Foundry agent when adding HCP profiles

**Goal:** When admin creates/updates/deletes an HCP profile, the system automatically syncs a corresponding AI Foundry Agent. Digital Human Realtime Agent mode uses the HCP's agent_id to drive conversations. HCP profiles admin page is redesigned to table format with Agent sync status.
**Requirements**: HCP-01, HCP-02, COACH-06, COACH-07, UI-06, PLAT-01, PLAT-03
**Depends on:** Phase 10
**Plans:** 3/3 plans complete

**Success Criteria** (what must be TRUE):
  1. Admin can create/update/delete HCP profiles and the system automatically creates/updates/deletes a corresponding AI Foundry Agent
  2. Agent sync status (synced/pending/failed/none) is visible per HCP profile in the admin table with error details on hover
  3. Failed agent sync does not prevent HCP profile save -- status shows as "failed" with retry option
  4. Token broker returns per-HCP agent_id for Digital Human Realtime Agent mode sessions
  5. HCP profiles page uses sortable table layout with agent status column replacing the previous list+editor layout
  6. All new UI text externalized to i18n in both en-US and zh-CN
  7. All new code has unit tests with >=95% coverage maintained

Plans:
- [x] 11-01-PLAN.md -- Backend foundation: HcpProfile agent columns, Alembic migration, agent_sync_service (AI Foundry REST API wrapper), schema updates
- [x] 11-02-PLAN.md -- Backend wiring: HCP CRUD sync hooks, retry-sync endpoint, token broker HCP agent_id sourcing, integration tests
- [x] 11-03-PLAN.md -- Frontend: TypeScript types, API client, hooks, i18n keys, HcpTable component, HCP profiles page rewrite (table layout)

**UI hint**: yes

### Phase 12: Voice Realtime API & Agent Mode Integration

**Goal:** Each HCP profile becomes a complete "digital persona" with per-HCP voice, avatar, and conversation parameters. The token broker returns all settings in one response. MRs get automatic mode selection (Digital Human Realtime Agent as default) with graceful fallback to voice-only or text. Admin configures HCP digital personas via a tabbed editor.
**Requirements**: VOICE-12-01, VOICE-12-02, VOICE-12-03, VOICE-12-04, VOICE-12-05, VOICE-12-06
**Depends on:** Phase 11
**Plans:** 4/4 plans complete

**Success Criteria** (what must be TRUE):
  1. Admin can configure per-HCP voice settings (voice name, temperature), avatar settings (character, style), and conversation parameters (turn detection, noise suppression, echo cancellation) via tabbed HCP editor
  2. Token broker returns all per-HCP voice/avatar settings when hcp_profile_id is provided, falls back to global defaults when not
  3. New HCPs get smart defaults (voice "Ava", avatar "Lori-casual", temp 0.9, Server VAD) without manual configuration
  4. MR does NOT see a mode picker -- system auto-selects best mode based on HCP config and service availability
  5. Fallback chain works: Digital Human Realtime Agent -> Voice-only Realtime -> Text, with toast notification and persistent mode status indicator
  6. HCP table shows Voice & Avatar column with badge pair showing per-HCP configuration
  7. Agent instructions support admin override via Agent tab (D-02)
  8. All new UI text externalized to i18n in both en-US and zh-CN

Plans:
- [x] 12-01-PLAN.md -- Backend foundation: Alembic migration (13 voice/avatar columns), ORM model, Pydantic schemas, token broker per-HCP wiring, API endpoint extension
- [x] 12-02-PLAN.md -- Frontend admin: TypeScript types, API client, i18n keys, VoiceAvatarTab, AgentTab, HCP editor tabbed rewrite, HCP table Voice+Avatar column
- [x] 12-03-PLAN.md -- Frontend voice session: ModeStatusIndicator, auto-mode resolution, fallback chain, per-HCP token wiring, useVoiceLive per-HCP config
- [x] 12-04-PLAN.md -- Backend tests, seed data with per-HCP digital persona configurations, full build verification

**UI hint**: yes

### Phase 13: Voice Live Instance & Agent Voice Management

**Goal:** Admin can create/manage Voice Live instances (select generative AI model from GPT-4o/4.1/5 tiers), bind Voice Live to HCP Agents, enable Voice mode on agents, and configure speech input/output/avatar parameters — matching AI Foundry portal's Voice Live workflow end-to-end via Azure AI Projects SDK. The platform automates the full chain: HCP Profile → Agent → Voice Live instance → Voice mode → Speech/Avatar config.
**Requirements**: VOICE-13-01, VOICE-13-02, VOICE-13-03, VOICE-13-04, VOICE-13-05
**Depends on:** Phase 12
**Plans:** 3/3 plans complete

Plans:
- [x] 13-01-PLAN.md -- Backend foundation: Alembic migration (voice_live_model), ORM/schema extension, VOICE_LIVE_MODELS constant, token broker per-HCP model, GET /models endpoint, tests
- [x] 13-02-PLAN.md -- Frontend types, VoiceLiveModelSelect component, VoiceAvatarTab model select, HCP editor schema, HCP table model badge, i18n keys
- [x] 13-03-PLAN.md -- VoiceLiveChainCard, Voice Live Management page, route + sidebar nav, batch re-sync, build verification

### Phase 14: HCP Agent Refactor — VL Instance Read-Only Reference + Knowledge/Tools Config

**Goal:** 重构 HCP 编辑器对齐 AI Foundry Agent 页面设计。Voice Live 配置从 HCP 编辑器移至只读引用（来自 VL Instance），HCP 编辑器新增 Knowledge（课程/产品知识库）和 Tools（Function Call）配置区域。VL Management 页成为语音/数字人配置的唯一编辑入口，HCP 编辑器聚焦 Agent 属性（Instructions/Prompt、Knowledge、Tools）。
**Requirements**: HCP-14-01, HCP-14-02, HCP-14-03, HCP-14-04, HCP-14-05, HCP-14-06
**Depends on:** Phase 13
**Plans:** 4/4 plans complete

**Success Criteria** (what must be TRUE):
  1. HCP Voice Tab 改为只读预览 + VL Instance 下拉选择器（不可在 HCP 中编辑 VL 配置）
  2. HCP 编辑器新增 Knowledge 区域（添加/移除知识库，对齐 AI Foundry Knowledge section）
  3. HCP 编辑器新增 Tools 区域（Function Call 配置，对齐 AI Foundry Tools section）
  4. Avatar 缩略图使用真人面部插画替代字母圆圈
  5. VL Management 页完善为 VL Instance CRUD + 在线测试 + HCP 分配
  6. 前后端测试覆盖 + i18n（en-US + zh-CN）

**UI hint**: yes

Plans:
- [x] 14-01-PLAN.md -- Backend unassign endpoint, frontend API/hook extension, i18n keys for Phase 14
- [x] 14-02-PLAN.md -- VL Management page rewrite with rich CRUD dialog (VlInstanceDialog), enhanced instance card
- [x] 14-03-PLAN.md -- HCP Voice Tab simplification (read-only preview + instance selector), Knowledge/Tools placeholder tabs
- [x] 14-04-PLAN.md -- Backend + frontend tests, build verification, human visual checkpoint

### Phase 15: HCP Editor Agent Config Center

**Goal:** 重构 HCP 编辑器为 Agent 配置中心，对齐 Azure AI Foundry Agent 编辑体验。移除空 Knowledge/Tools tab，Voice & Avatar tab 升级为完整 Agent 配置布局：Model Deployment 选择器、Voice Mode 开关+VL Instance 关联、Instructions 自动生成+可编辑覆盖、右侧 Playground 预览面板（数字人/音波球+Start 测试）。
**Requirements**: HCP-15-01, HCP-15-02, HCP-15-03, HCP-15-04, HCP-15-05
**Depends on:** Phase 14
**Plans:** 3/3 plans complete

Plans:
- [x] 15-01-PLAN.md -- Backend preview-instructions endpoint, to_prompt_dict fix, i18n keys, left panel components (AgentConfigLeftPanel + InstructionsSection)
- [x] 15-02-PLAN.md -- PlaygroundPreviewPanel component, VoiceAvatarTab rewrite (2-panel grid), hcp-profile-editor tab cleanup (remove Knowledge/Tools)
- [x] 15-03-PLAN.md -- Backend tests, full build verification, visual checkpoint for Agent Config Center layout


**Success Criteria** (what must be TRUE):
  1. HCP 编辑器只有 Profile 和 Voice & Avatar 两个 tab（Knowledge/Tools 空 tab 已移除）
  2. Voice & Avatar tab 左侧包含 Model Deployment 选择器、Voice Mode 开关+VL Instance 选择、Instructions 区域（自动生成+可编辑 override）
  3. Voice & Avatar tab 右侧为 Playground 预览面板，根据 avatar 配置显示数字人形象或音波球，含 Start 测试按钮
  4. Instructions 区域可通过魔法棒按钮调用 build_agent_instructions 重新生成
  5. 前后端测试覆盖 + i18n（en-US + zh-CN）+ TypeScript 编译通过

**UI hint**: yes

### Phase 17: Agent Knowledge Base — Foundry IQ Integration

**Goal:** HCP Agent 知识库配置（Agent 能力定义范畴），对齐 Azure AI Foundry Knowledge 配置体验。Admin 可在 HCP 编辑器中列出 AI Foundry Project 的 AI Search Connections 和已有 Knowledge Base，选择并绑定到 HCP Agent。知识库配置通过 MCPTool 同步到 AI Foundry Agent，使 Agent 在对话中自动使用 Foundry IQ RAG 检索知识。KB 的创建/维护/文档上传属于知识管理模块职责，不在本 phase 范围。
**Requirements**: KB-17-01, KB-17-02, KB-17-03, KB-17-04, KB-17-05
**Depends on:** Phase 16
**Plans:** 3/3 plans complete

Plans:
- [x] 17-01-PLAN.md -- Backend foundation: Alembic migration (hcp_knowledge_configs), ORM model, Pydantic schemas, knowledge_base_service, API router, agent_sync tools extension
- [x] 17-02-PLAN.md -- Frontend: TypeScript types, API client, TanStack Query hooks, i18n keys, ConnectKbDialog, KnowledgeTab, HCP editor integration
- [x] 17-03-PLAN.md -- Integration wiring: agent sync e2e test, frontend component tests, build verification, visual checkpoint

**Success Criteria** (what must be TRUE):
  1. Admin 可在 HCP 编辑器 Knowledge tab 中列出 AI Foundry Project 的 AI Search Connections，选择 Connection 后列出其中已有的 Knowledge Base（对齐 AI Foundry "Connect to Foundry IQ" 流程）
  2. Admin 选择 Connection + KB 后绑定到 HCP Agent，一个 Agent 可绑定多个 KB
  3. 知识库配置通过 MCPTool 同步到 AI Foundry Agent definition 的 tools 参数，Agent 在对话中自动使用 Foundry IQ RAG 检索知识
  4. HCP 编辑器 Knowledge tab 显示已绑定的知识库列表（名称、connection、状态），支持解绑操作
  5. 前后端测试覆盖 + i18n（en-US + zh-CN）+ TypeScript/Ruff 构建通过

**UI hint**: yes

### Phase 18: Training Material Download & Preview

**Goal:** 为培训材料模块添加文件下载和在线预览功能。后端暴露安全的文件下载 API（不泄露本地文件系统路径），前端支持 PDF 在线预览（iframe/embed）和 DOCX/XLSX 文件下载。修复 `storage_url` 信息泄露问题，使用安全的下载 URL 替代本地路径。
**Requirements**: MAT-18-01, MAT-18-02, MAT-18-03, MAT-18-04
**Depends on:** Phase 05
**Plans:** 3 plans

Plans:
- [x] 18-01-PLAN.md -- Backend file download API endpoint, storage_url security fix, download tests (3/3, completed 2026-04-10)
- [x] 18-02-PLAN.md -- Frontend PDF preview dialog, DOCX/XLSX download, i18n, TypeScript types (3/3, completed 2026-04-10)
- [x] 18-03-PLAN.md -- Integration tests, build verification, ROADMAP update (3/3, completed 2026-04-10)

**Success Criteria** (what must be TRUE):
  1. 后端提供 `GET /api/v1/materials/{material_id}/versions/{version_id}/download` 端点，返回 `FileResponse`（流式传输原始文件），支持 Content-Disposition header（inline 预览或 attachment 下载）
  2. `MaterialVersionOut` schema 中 `storage_url` 字段替换为安全的相对下载 URL（如 `/api/v1/materials/{id}/versions/{vid}/download`），不再泄露本地文件系统路径
  3. 前端 PDF 文件支持在线预览（弹窗/侧栏中使用 iframe 或 PDF.js 渲染），无需下载即可查看内容
  4. 前端 DOCX/XLSX 文件点击后直接触发浏览器下载
  5. 版本历史对话框中每个版本显示"预览"（PDF）或"下载"按钮
  6. 前后端测试覆盖 + i18n（en-US + zh-CN）+ TypeScript/Ruff 构建通过

**UI hint**: yes

### Phase 19: AI Coach Skill Module — Skill lifecycle management, material-to-skill conversion, Skill Hub, and HCP Agent skill assignment for SOP-driven training

**Goal:** 构建 AI Coach Skill 模块，实现 Skill 全生命周期管理（创建、编辑、发布、归档）。用户可上传一个或多个培训材料（文档、PPT等），系统自动将其转换为结构化的培训 Skill（包含 SOP、考核内容、知识点等）；也支持直接上传已打包的 Skill 压缩包。Skill Hub 集中展示所有可用 Skill 的名称和描述。管理员可将 Skill 按场景分配给 HCP Agent，训练过程中 HCP Agent 依据 SOP 内容与 MR 用户交互，确保考核内容的完整性和正确性。

**Key deliverables:**
- Skill 数据模型（Skill、SkillVersion、SkillMaterial、SkillAssignment）
- 材料上传与 AI 自动转换为 Skill（含 SOP 提取）
- Skill 压缩包导入/导出
- Skill Hub 前端页面（列表、搜索、详情）
- Skill → HCP Agent 分配管理
- 训练会话中 Agent 基于 Skill SOP 驱动交互逻辑

**Key deliverables:**
- Skill 数据模型（Skill、SkillVersion、SkillMaterial、SkillAssignment + 评测字段）
- 材料上传与 AI 自动转换为 Skill（含 SOP 提取）
- **Layer 1 自动结构检查**（即时规则引擎：SOP完整性、考核覆盖度、知识点、必填字段）
- **Layer 2 AI 质量评估**（Azure OpenAI 六维度打分：SOP完整性/考核覆盖度/知识准确性/难度合理性/对话逻辑性/可执行性）
- **发布门控**（L1 必须 PASS + L2 >= 50 分方可发布，50-69 警告确认）
- Skill 压缩包导入/导出
- Skill Hub 前端页面（列表、搜索、详情 + 质量评分展示）
- Skill → HCP Agent 分配管理
- 训练会话中 Agent 基于 Skill SOP 驱动交互逻辑
- **Skill 预览与客户反馈流程**（Admin 创建 Skill 后可分享预览链接给客户查看，收集反馈意见后调整）

**Requirements**: D-01, D-02, D-03, D-04, D-05, D-06, D-07, D-08, D-09, D-10, D-11, D-12, D-13, D-14, D-15, D-16, D-17, D-18, D-19, D-20, D-21, D-22, D-23, D-24, D-25, D-26, D-27
**Depends on:** Phase 18
**Plans:** 6/8 plans executed

**Success Criteria** (what must be TRUE):
  1. Admin can create Skills by uploading materials (PDF/DOCX/PPTX/TXT/MD) and the system converts them to structured SOP content
  2. Skill Hub page shows card grid of all Skills with status badges, search, and filtering
  3. Skill editor provides 4 tabs: Content (dual-mode SOP editing), Resources (file tree), Quality (L1+L2 results), Settings
  4. L1 structure check runs instantly (rule-based), L2 AI quality evaluation runs async with 6 dimensions
  5. Publish gate enforces L1 PASS + L2 >= 50; 50-69 allows publish with warning, <50 blocks
  6. Admin can associate published Skills with Scenarios; SkillManager injects SOP into Agent instructions
  7. ZIP import/export follows agentskills.io spec (SKILL.md + references/ + scripts/ + assets/)
  8. Backend tests pass (25+), frontend TypeScript compiles, backend ruff lint passes

Plans:
- [x] 19-01-PLAN.md -- Backend data foundation: Skill/SkillVersion/SkillResource models, strict state machine, schemas, migration, CRUD service, API routes
- [x] 19-02-PLAN.md -- Material-to-Skill conversion: durable job processing, text extraction, semantic chunking, Azure OpenAI SOP extraction, AI feedback regeneration
- [x] 19-03-PLAN.md -- Quality gates: L1 structure validation with configurable rules, L2 AI quality evaluation with content hash, transactional publish gate
- [x] 19-04-PLAN.md -- Frontend data layer + Skill Hub: TypeScript types, API client with query-key factory, TanStack hooks, i18n, Skill Hub page
- [x] 19-05-PLAN.md -- Skill Editor MVP: SopEditor (dual-mode), FileTreeView, ConversionProgress, Content + Resources tabs
- [x] 19-06-PLAN.md -- Skill Editor Advanced: QualityRadarChart, QualityScoreCard, PublishGateDialog, Quality + Settings tabs, Publish flow
- [ ] 19-07-PLAN.md -- Scenario-Skill integration: skill_version_id FK, SkillManager, sandboxed script_runner, prompt_builder, agent_sync
- [ ] 19-08-PLAN.md -- ZIP import/export with security hardening, comprehensive backend tests, human verification

### Phase 20: Skill Dry Run Simulation — AI 模拟测试验证 Skill 可执行性

**Goal:** 构建 Skill Dry Run 模拟测试系统（评测 Layer 3）。Admin 创建 Skill 后，可启动 Dry Run 模式，系统用 AI 分别扮演 MR 和 HCP Agent 执行一轮完整的模拟对话，验证 Skill SOP 是否能驱动有效、完整、有意义的训练交互。输出模拟对话记录 + SOP 步骤覆盖率报告 + 可执行性评分，帮助 Admin 在发布前发现 SOP 设计缺陷。

**Key deliverables:**
- Dry Run 模拟引擎（AI 扮演 MR + HCP Agent 自动对话）
- SOP 步骤覆盖率追踪（每个 SOP step 是否被触达）
- 模拟对话记录存储与回放
- Dry Run 结果报告页面（覆盖率、可执行性评分、问题标注）
- 多轮 Dry Run 历史对比
- Skill 编辑器中集成 Dry Run 入口

**Requirements**: DR-01, DR-02, DR-03, DR-04, DR-05, DR-06, DR-07, DR-08
**Depends on:** Phase 19
**Plans:** 5/5 plans complete

**Success Criteria** (what must be TRUE):
  1. Admin can trigger a Dry Run from the Skill Editor; system simulates a complete MR-HCP conversation using AI agents
  2. SOP steps are extracted from Skill content and tracked for coverage during simulation
  3. Dry Run report shows executability score, SOP coverage percentage, and identified issues
  4. Report page provides 3 sub-tabs: Conversation transcript, SOP Coverage map, Issues list
  5. Quality tab in Skill Editor shows Dry Run history with comparison chart across multiple runs
  6. All dry run data persists to database (DryRun + DryRunMessage tables)
  7. Backend tests cover engine helpers and API endpoints
  8. i18n complete in both en-US and zh-CN

Plans:
- [x] 20-01-PLAN.md -- Backend data foundation: DryRun/DryRunMessage ORM models, Alembic migration, Pydantic schemas, CRUD service, REST API
- [x] 20-02-PLAN.md -- Dry Run simulation engine: AI MR+HCP orchestration, SOP extraction, coverage tracking, background task
- [x] 20-03-PLAN.md -- Frontend data layer: TypeScript types, API client, TanStack Query hooks, i18n translations
- [x] 20-04-PLAN.md -- Dry Run Report page: 6 shared components, report page with 3 sub-tabs, route registration
- [x] 20-05-PLAN.md -- Skill Editor integration: DryRunButton, DryRunProgress, DryRunHistoryList, backend tests

**UI hint**: yes

### Phase 21: Scoring Criteria Refactor — 评分标准模块重构，动态维度驱动

**Goal:** 重构评分标准模块，消除5个评分维度在 Scenario 模型、Scoring Engine Prompt、Mock Score Generator、前端 ScoringWeights 组件中的硬编码。将 ScoringRubric 升级为评分的唯一权威来源（Single Source of Truth），支持管理员自定义评分维度名称/数量/权重/评分标准，所有评分流程（LLM评分、Mock评分、前端展示）统一从 Rubric 动态读取。

**Key deliverables:**
- 将 Scenario 模型中5个固定权重列迁移为 rubric_id 外键引用
- Scoring Engine Prompt 模板改为从 Rubric 动态生成维度指令
- Mock Score Generator 支持任意维度数量
- 前端 ScoringWeights 组件改为从 Rubric 动态渲染
- 评分反馈页面（RadarChart、DimensionBars、FeedbackCard）支持动态维度
- 确保 Skill Assessment Criteria 与新 Rubric 系统兼容
- 数据迁移：将现有 Scenario 权重数据迁移到 Rubric 记录

**Requirements**: SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05
**Depends on:** Phase 03
**Plans:** 3 plans

Plans:
- [ ] 21-01-PLAN.md -- Backend: Scenario model rubric_id FK, scoring engine dynamic prompt, mock scorer, analytics fix, seed data
- [ ] 21-02-PLAN.md -- Frontend: TypeScript types, dimension display utility, ScenarioEditor rubric selector, i18n keys
- [ ] 21-03-PLAN.md -- Integration: Alembic migration push, backend test fixes, frontend build verification

**Success Criteria** (what must be TRUE):
  1. Admin 可以创建含任意数量自定义维度的 Rubric，每个维度有名称、权重、评分标准、满分值
  2. Scenario 通过 rubric_id 引用 Rubric，不再有硬编码的 weight_* 列
  3. LLM 评分引擎从 Rubric 动态构建 prompt，维度名称和评分标准来自 Rubric 配置
  4. Mock 评分生成器支持任意维度数量，不依赖硬编码维度名
  5. 前端评分反馈页面（RadarChart、DimensionBars、FeedbackCard）根据 Rubric 维度动态渲染
  6. 前端 ScoringWeights 组件从 Rubric 维度动态生成滑块，不再硬编码5个维度
  7. Alembic 数据迁移将现有 Scenario 权重数据转换为 Rubric 记录
  8. 所有现有评分测试通过，新增动态维度场景的测试覆盖

**UI hint**: yes


### Phase 22: 对Scenarios 模块进行二次重构

**Goal:** Scenarios module second refactor: Editor full-page route-based, I18N complete, metadata to tags system, state machine (draft/active/archived), skill_id NOT NULL, global hardcoded enum elimination via DB config table.
**Requirements**: D-01, D-02, D-03, D-04, D-05, D-06, D-07
**Depends on:** Phase 21
**Plans:** 12 plans (6 original + 6 gap closure)

Plans:
- [x] 22-01-PLAN.md -- Backend model prep and full-page editor scaffolding
- [x] 22-02-PLAN.md -- Backend state machine and tags foundation
- [x] 22-03-PLAN.md -- Backend system enums and skill NOT NULL
- [x] 22-04-PLAN.md -- Frontend types, hooks, and editor page
- [x] 22-05-PLAN.md -- Frontend table, list page, and wiring
- [x] 22-06-PLAN.md -- I18N global audit (non-scenario pages)
- [ ] 22-07-PLAN.md -- [Gap closure] Backend model + schema + migration chain fix (tags, skill_id, archived)
- [ ] 22-08-PLAN.md -- [Gap closure] Backend service + API (state machine transitions, tags serialization)
- [ ] 22-09-PLAN.md -- [Gap closure] System Enums full stack (model, service, API, frontend page)
- [ ] 22-10-PLAN.md -- [Gap closure] Frontend types + API + hooks update (tags, archived, transitions)
- [ ] 22-11-PLAN.md -- [Gap closure] Frontend list page + table wiring (navigate, tags display, transitions)
- [ ] 22-12-PLAN.md -- [Gap closure] I18N for scenario module (locale keys, remove defaultValue)

**Success Criteria** (what must be TRUE):
  1. State machine enforces draft -> active -> archived transitions via dedicated POST /transition endpoint
  2. System enums table replaces all hardcoded frontend constants (products, specialties, difficulties) with DB-driven values
  3. Scenario model uses tags JSON array instead of product/therapeutic_area columns
  4. skill_id is NOT NULL on Scenario model with RESTRICT on delete
  5. Full-page route-based scenario editor replaces Dialog editor (old editor deleted)
  6. I18N audit eliminates all hardcoded text and defaultValue fallbacks from scenario module

**UI hint**: yes

### Phase 23: Complete training session with digital human - full implementation and refactoring

**Goal:** [To be planned]
**Requirements**: TBD
**Depends on:** Phase 22
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 23 to break down)


### Phase 24: Session Skill Focus + Azure CU Evaluation — 评估模块重构

**Goal:** 两大核心改进：(1) 培训 session 中 Agent 通过 thread 级 additional_instructions 动态聚焦当前 Skill SOP 内容（不修改 Agent 定义），包括 SOP 进度跟踪和分级偏题处理；(2) Session 结束后统一使用 Azure Content Understanding 自定义 Analyzer 评估所有维度（替代 LLM scoring_engine），内容评估走 CU transcript，语音评估走 CU audio，分层合并为综合评分。
**Requirements**: D-01, D-02, D-03, D-04, D-05, D-06, D-07, D-08, D-09, D-10, D-11, D-12, D-13, D-14, D-15, D-16
**Depends on:** Phase 23
**Plans:** 5/5 plans complete

**Success Criteria** (what must be TRUE):
  1. Session 创建时，系统从 Skill SOP 生成 focus_instruction 快照并持久化到 DB (D-03)
  2. 每次用户发消息后，LLM 判断当前 SOP 步骤，更新 additional_instructions 中的进度提示 (D-05, D-06)
  3. Agent 严格围绕 SOP 内容讨论，轻微偏离温和引导，完全无关话题硬性阻断 (D-04)
  4. Agent 定义完全不修改，Skill Focus 仅通过 run 级 additional_instructions 注入 (D-01)
  5. Rubric 保存时自动创建/更新对应的 CU Custom Analyzer (D-09)
  6. Session 结束后，内容评估提交 transcript JSON 给 CU，语音评估提交音频给 CU (D-10)
  7. 评分分层合并：内容总分 * content_weight + 语音总分 * voice_weight (D-11, D-12)
  8. 纯文本 session 仅做内容评估 (D-13)；语音 session 做双维度评估 (D-14)
  9. 前端 Rubric 编辑器新增 content_weight/voice_weight 滑块 (D-12)
  10. 前端评分反馈页显示内容/语音类别分项得分

Plans:
- [x] 24-01-PLAN.md -- Backend data foundation: Alembic migration (focus_instruction, sop_current_step, content_weight, voice_weight, cu_analyzer_ids), ORM + schema extensions
- [x] 24-02-PLAN.md -- Skill Focus Service: compose_focus_instruction, extract_sop_steps, detect_sop_step (LLM classification)
- [x] 24-03-PLAN.md -- CU Evaluation Service: analyzer schema builder, CU scoring (content + voice), layered merge, rubric sync hook
- [x] 24-04-PLAN.md -- Session integration: focus_instruction snapshot on create, SOP progress per message, scoring_service uses CU
- [x] 24-05-PLAN.md -- Frontend (rubric weight sliders, scoring subtotal badges, i18n) + backend unit tests

**UI hint**: yes

### Phase 25: Refactor user training pages - fix data display, scoring logic, and dashboard/reports deduplication

**Goal:** Fix remaining data display issues in user training pages (scoring feedback shows raw IDs, hardcoded mode), resolve Dashboard/Reports content duplication, and ensure proper test coverage for all refactored pages.
**Requirements**: P25-01, P25-02, P25-03, P25-04, P25-05
**Depends on:** Phase 24
**Plans:** 2 plans

Plans:
- [ ] 25-01-PLAN.md -- Fix scoring feedback metadata (scenario_name, mode) + deduplicate Dashboard/Reports stat overlap
- [ ] 25-02-PLAN.md -- Update test suites for scoring-feedback, reports, and dashboard changes

**Success Criteria** (what must be TRUE):
  1. Scoring feedback page displays scenario name (not UUID) and localized session mode (not hardcoded "F2F")
  2. Reports page uses compact summary bar instead of duplicate 4-card stat grid from Dashboard
  3. Dashboard includes link to Reports page for detailed analysis
  4. All frontend tests pass with new assertions covering the refactored behavior
  5. TypeScript compiles and frontend builds without errors

**UI hint**: yes
### Phase 26: Add voice-live-webrtc transport option as alternative to WebSocket

**Goal:** Add WebRTC as an alternative real-time audio transport for Voice Live sessions. Browser connects directly to Azure for lower latency. WebSocket proxy remains default.
**Requirements**: D-01, D-02, D-03, D-04, D-05, D-06, D-07, D-08, D-09, D-10, D-11
**Depends on:** Phase 25
**Plans:** 3 plans (complete)

Plans:
- [x] 26-01-PLAN.md -- Backend WebRTC session endpoint (token broker + signaling URL assembly) (2/2 tasks, completed 2026-05-22)
- [x] 26-02-PLAN.md -- Frontend useVoiceLiveWebRTC hook (RTCPeerConnection, signaling WS, data channel) (2/2 tasks, completed 2026-05-22)
- [x] 26-03-PLAN.md -- UI transport selector integration (VoiceTransportSelect, dual hook wiring, i18n) (2/2 tasks, completed 2026-05-22)


### Phase 27: Prompt Optimizer & Unified Prompt Management

**Goal:** Integrate the open-source prompt-optimizer via a Docker/Container Apps sidecar and MCP client, migrate all 9 project prompts into a unified versioned registry (PromptTemplate/PromptVersion/PromptOptimizationRun), record every optimization run, and expose a single admin UI to browse, edit, AI-optimize (with diff), adopt, and roll back any prompt.
**Requirements**: PROMPT-01, PROMPT-02, PROMPT-03, PROMPT-04, PROMPT-05, PROMPT-06
**Depends on:** Phase 21 (ScoringRubric versioning precedent)
**Plans:** 8/8 plans complete

Plans:
- [x] 27-01-PLAN.md -- Prompt Registry foundation: 3 ORM models + migration, defaults catalog, get_prompt resolver, seed, tests
- [x] 27-02-PLAN.md -- Optimizer sidecar + MCP client + stateless /prompts/optimize + Azure /v1 feasibility gate
- [x] 27-03-PLAN.md -- Migrate all builders to registry (get_prompt) with snapshot regression (no behavior drift)
- [x] 27-04-PLAN.md -- Prompt management REST API: versions, activate/rollback, optimization run recording, adopt
- [x] 27-05-PLAN.md -- Frontend unified management UI: list + editor, AI optimize/diff/adopt, version history, E2E
- [x] 27-06-PLAN.md -- Per-entity prompts (rubric, conference) reuse + Azure internal Container App deploy
- [x] 27-07-PLAN.md -- Create New Prompt: POST /prompts + list-page create dialog (was Phase 28 Plan 01)
- [x] 27-08-PLAN.md -- View historical version content: read-only version content viewer (was Phase 28 Plan 02)

**Success Criteria** (what must be TRUE):
  1. Every one of the 9 project prompts is registered, versioned, and admin-editable from a single UI
  2. Admin can AI-optimize any prompt, compare original vs optimized, and adopt it as a new version
  3. Every optimization is recorded as a run (original, result, mode, model, time) and version history supports rollback
  4. Migrating builders to the registry causes zero output change with default (seeded) content
  5. The prompt-optimizer runs as an internal-only service backed by Azure OpenAI with secrets from Key Vault
  6. Admin can create a brand-new prompt from the list UI (not limited to optimizing existing ones) and view the text content of any historical version

**UI hint**: yes
