# Requirements: AI Coach Platform (BeiGene)

**Defined:** 2026-03-24
**Core Value:** MRs can practice realistic conversations with AI-powered digital HCPs and receive immediate, multi-dimensional feedback to improve their communication skills — anytime, without needing a real HCP or trainer.

## Guiding Principles

> **Architecture-first: configurable, pluggable, component-based** is the highest priority.
> Features may be incomplete, but config options, interfaces, and extension points MUST exist from day 1.
> Common components are reusable — changes happen at component level, not page level.

## v1 Requirements

### Architecture (ARCH)

- [x] **ARCH-01**: System uses pluggable adapter pattern for all AI services (LLM, STT, TTS, Avatar) — providers can be swapped via configuration without code changes
- [x] **ARCH-02**: All features are component-based and configurable — feature toggles control availability per deployment
- [x] **ARCH-03**: Backend services use dependency injection — any service can be replaced with a mock, alternative provider, or upgraded implementation
- [x] **ARCH-04**: Frontend uses shared design system component library extracted from Figma Design System — all pages reuse common components with property variations
- [x] **ARCH-05**: Azure service connections are configurable per environment — endpoints, keys, models, regions are config, not code

### User Interface (UI)

- [x] **UI-01**: Shared component library based on Figma "Design System for SaaS" — buttons, cards, inputs, charts, navigation as reusable components
- [x] **UI-02**: Login page and app layout shell implemented from Figma "Design Login and Layout Shell" — sidebar navigation, header, responsive shell
- [x] **UI-03**: F2F HCP Training page implemented from Figma "F2F HCP Training Page Design" — chat area, HCP display, controls, coaching hints panel
- [x] **UI-04**: MR Dashboard implemented from Figma "Medical Representative Dashboard" — score overview, recent sessions, skill radar chart
- [x] **UI-05**: Scenario Selection page implemented from Figma "Scenario Selection Page Design" — scenario cards, filters, difficulty indicators
- [x] **UI-06**: Additional pages (admin, config, reports, session history) follow same design principles as Figma pages — self-developed using shared components
- [x] **UI-07**: All UI text externalized via react-i18next — Chinese (zh-CN) and English (en-US) supported from day 1

### Authentication (AUTH)

- [x] **AUTH-01**: User can log in with simple username and password
- [x] **AUTH-02**: User session persists across browser refresh via JWT
- [x] **AUTH-03**: Two roles: User (MR) and Admin — role-based route protection
- [x] **AUTH-04**: Auth module uses dependency injection — architecture ready for Azure AD, Teams SSO, or Enterprise WeChat integration later

### HCP & Scenario Configuration (HCP)

- [x] **HCP-01**: Admin can create and edit HCP profiles with name, specialty, personality type, emotional state, communication style, knowledge background
- [x] **HCP-02**: Admin can define typical objections and interaction rules per HCP profile
- [x] **HCP-03**: Admin can create and edit training scenarios with product, therapeutic area, key messages, and difficulty level
- [x] **HCP-04**: Admin can assign HCP profiles to scenarios and configure scoring dimension weights per scenario
- [x] **HCP-05**: Admin can set pass/fail threshold per scenario with weighted scoring criteria totaling 100%

### F2F Coaching Simulation (COACH)

- [x] **COACH-01**: User can start a text-based F2F coaching session with an AI-powered HCP based on selected scenario
- [x] **COACH-02**: AI HCP responds in character (personality, knowledge, objections) as defined by HCP profile and scenario context
- [x] **COACH-03**: System tracks key message delivery in real-time — checklist shows which messages were delivered and which were missed
- [x] **COACH-04**: User can use voice input (Azure Speech STT) — speech recognized and sent as text to AI HCP (zh-CN + en-US)
- [x] **COACH-05**: AI HCP responses are spoken via Azure Speech TTS — natural-sounding voices in Chinese and English
- [x] **COACH-06**: Voice interaction supports GPT Realtime API (WebSocket) for sub-1s conversational latency as configurable premium option
- [x] **COACH-07**: Azure AI Avatar renders digital human visual for HCP as configurable premium option — falls back to TTS-only when disabled or unavailable
- [x] **COACH-08**: Real-time coaching hints displayed in side panel during conversation — contextual suggestions based on conversation progress
- [x] **COACH-09**: Conversations are immutable once completed — only scoring and feedback can be added after completion

### Scoring & Feedback (SCORE)

- [x] **SCORE-01**: System scores completed sessions across 5-6 configurable dimensions (key message delivery, objection handling, communication skills, product knowledge, scientific accuracy)
- [x] **SCORE-02**: Scoring uses Azure OpenAI to analyze conversation transcript against scenario criteria and HCP expectations
- [x] **SCORE-03**: Post-session feedback report shows strengths and weaknesses per dimension with specific conversation quotes
- [x] **SCORE-04**: Post-session feedback includes actionable improvement suggestions per dimension
- [x] **SCORE-05**: Scoring dimension weights are configurable per scenario — admin sets relative importance via weighted sliders

### Conference Mode (CONF)

- [x] **CONF-01**: User can start a conference presentation mode with multiple virtual HCP audience members
- [x] **CONF-02**: Multiple AI HCPs ask questions from audience — questions queue with turn management
- [x] **CONF-03**: Conference session includes live transcription display
- [x] **CONF-04**: Conference sessions are scored using the same multi-dimensional scoring system as F2F

### Content Management (CONTENT)

- [x] **CONTENT-01**: Admin can upload training materials (PDF, Word, Excel) organized by product and therapeutic area
- [x] **CONTENT-02**: Uploaded materials feed into AI knowledge base for more accurate HCP simulation (RAG-style grounding)
- [x] **CONTENT-03**: Training materials support versioning and folder organization

### Analytics & Reports (ANLYT)

- [x] **ANLYT-01**: User can view session history — list of past sessions with date, scenario, score, duration
- [x] **ANLYT-02**: User can view personal performance trends — score improvement over time per dimension
- [x] **ANLYT-03**: Admin can view organization-level analytics — BU comparisons, skill gap heatmaps, training completion rates
- [x] **ANLYT-04**: System recommends next training scenarios based on user's scoring history and identified weaknesses
- [x] **ANLYT-05**: Reports and dashboards use Recharts radar/spider charts for multi-dimensional score visualization

### Platform (PLAT)

- [x] **PLAT-01**: i18n framework (react-i18next) integrated from day 1 — all UI strings externalized, zh-CN and en-US
- [x] **PLAT-02**: Responsive web design — same app works on desktop, tablet, mobile, and Teams Tab (iframe)
- [x] **PLAT-03**: Admin can configure Azure service connections (OpenAI, Speech, Avatar, Content Understanding) from web UI with connection testing
- [x] **PLAT-04**: Per-region deployment supported — single codebase, per-region configuration for data residency (China, EU)
- [x] **PLAT-05**: Voice interaction mode (STT/TTS vs GPT Realtime vs Voice Live) configurable per deployment and per session

## v2 Requirements

### Extended Authentication

- **AUTH-V2-01**: Azure AD (Entra ID) SSO integration
- **AUTH-V2-02**: Microsoft Teams SSO for Teams Tab embedding
- **AUTH-V2-03**: Enterprise WeChat (企业微信) SSO integration
- **AUTH-V2-04**: Complex role hierarchy (DM, MSL, BU Head, Regional Director)

### Extended Features

- **EXT-01**: Teams Bot integration (full Bot Framework, adaptive cards)
- **EXT-02**: WeChat Mini Program frontend
- **EXT-03**: PDF/Excel export for reports and session transcripts
- **EXT-04**: Azure Voice Live API as unified premium voice+avatar path
- **EXT-05**: Custom analyzer configuration for Content Understanding

## Out of Scope

| Feature | Reason |
|---------|--------|
| Live video conferencing | Training simulator, not video call — use Avatar for visual |
| Mobile native app (iOS/Android) | Responsive web covers mobile; company phones have browsers |
| Multi-tenancy | Single tenant per-region; deploy separate instances if needed |
| Gamification (leaderboards, badges) | Professional training, not a game; focus on improvement trends |
| Conversation editing/retry from mid-point | Breaks simulation realism; MRs can "Try Again" with new session |
| Custom LLM fine-tuning | Prompt engineering + RAG achieves 90% of value at lower cost |
| Real-time collaborative training | Edge case; DMs review scores after, not observe live |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ARCH-01 | Phase 1 | Complete |
| ARCH-02 | Phase 1 | Complete |
| ARCH-03 | Phase 1 | Complete |
| ARCH-04 | Phase 1 | Complete |
| ARCH-05 | Phase 1 | Complete |
| UI-01 | Phase 1 | Complete |
| UI-02 | Phase 1 | Complete |
| UI-03 | Phase 2 | Complete |
| UI-04 | Phase 4 | Complete |
| UI-05 | Phase 2 | Complete |
| UI-06 | Phase 4 | Complete |
| UI-07 | Phase 1 | Complete |
| AUTH-01 | Phase 1 | Complete |
| AUTH-02 | Phase 1 | Complete |
| AUTH-03 | Phase 1 | Complete |
| AUTH-04 | Phase 1 | Complete |
| HCP-01 | Phase 2 | Complete |
| HCP-02 | Phase 2 | Complete |
| HCP-03 | Phase 2 | Complete |
| HCP-04 | Phase 2 | Complete |
| HCP-05 | Phase 2 | Complete |
| COACH-01 | Phase 2 | Complete |
| COACH-02 | Phase 2 | Complete |
| COACH-03 | Phase 2 | Complete |
| COACH-04 | Phase 3 | Complete |
| COACH-05 | Phase 3 | Complete |
| COACH-06 | Phase 3 | Complete |
| COACH-07 | Phase 3 | Complete |
| COACH-08 | Phase 2 | Complete |
| COACH-09 | Phase 2 | Complete |
| SCORE-01 | Phase 2 | Complete |
| SCORE-02 | Phase 2 | Complete |
| SCORE-03 | Phase 2 | Complete |
| SCORE-04 | Phase 2 | Complete |
| SCORE-05 | Phase 2 | Complete |
| CONF-01 | Phase 3 | Complete |
| CONF-02 | Phase 3 | Complete |
| CONF-03 | Phase 3 | Complete |
| CONF-04 | Phase 3 | Complete |
| CONTENT-01 | Phase 3 | Complete |
| CONTENT-02 | Phase 3 | Complete |
| CONTENT-03 | Phase 3 | Complete |
| ANLYT-01 | Phase 4 | Complete |
| ANLYT-02 | Phase 4 | Complete |
| ANLYT-03 | Phase 4 | Complete |
| ANLYT-04 | Phase 4 | Complete |
| ANLYT-05 | Phase 4 | Complete |
| PLAT-01 | Phase 1 | Complete |
| PLAT-02 | Phase 1 | Complete |
| PLAT-03 | Phase 2 | Complete |
| PLAT-04 | Phase 1 | Complete |
| PLAT-05 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 52 total
- Mapped to phases: 52
- Unmapped: 0

---
*Requirements defined: 2026-03-24*
*Last updated: 2026-03-24 after roadmap creation -- all requirements mapped to phases*


### Prompt Management (PROMPT)

- [x] **PROMPT-01**: Integrate the open-source prompt-optimizer via a sidecar + backend MCP client, backed by Azure OpenAI (unmodified upstream image; internal-only)
- [x] **PROMPT-02**: All project prompts are unified into a single versioned registry with a get_prompt resolver; builders read from the registry with default-equivalent fallback
- [x] **PROMPT-03**: Every AI optimization is recorded as an auditable run (original, optimized result, mode, template, model, time, actor)
- [x] **PROMPT-04**: Each prompt has an immutable version history supporting rollback to any prior version
- [x] **PROMPT-05**: A single admin UI manages all prompts: browse, edit, AI-optimize with diff, adopt, and roll back
- [x] **PROMPT-06**: Admins can create a brand-new prompt from the management UI (not limited to optimizing existing ones) and view the text content of any historical version
