# React Three Fiber and Capacitor plan for iOS Android and web

Updated October 12, 2026. Status: implementation started with the React profile
and pet experience and development native shell. This replaces the earlier
Unity migration proposal. No one is currently using the app; the owner has
authorized immediate retirement of the Unity runtime, navigation, validation
requirement and release jobs. Unity source and purchased originals remain
private/reference material. Physical-phone acceptance and production mobile
distribution are still incomplete.

Keep the existing React application as the complete product UI, add React Three
Fiber/Three.js for the companion experience, and package the same web UI with
Capacitor for iOS and Android. Django remains the shared backend. Every current
child, parent and staff workflow remains available in React; mobile releases
require working platform equivalents, not hidden controls or a partially
functional wrapper.

The [Cute Series asset review](../../../content/rpg/react-three-fiber-assets.md)
is a hard scope boundary. Base gameplay uses the recorded owned bird family and
woodland props. No milestone depends on creating models, fitting creature
outfits or authoring skeletal animations. Optional purchases and new
gameplay/progression rules are separate decisions.

## Application architecture

| Layer | Responsibility |
| --- | --- |
| Django and existing services | Accounts/family permissions, private content, saves, approvals, money/Coins, XP, ownership, progression, integrations and scheduled jobs |
| React DOM | Existing pages, forms, routing, drafts, administration, accessibility and API behavior on web and packaged mobile |
| R3F and Three.js | Lazy-loaded scene, prepared models, verified clips, camera, interactions and receipt-driven visual reactions |
| Capacitor | Packaged local web assets, native lifecycle/back/deep links, secure-session integration, device media/files and native notifications |
| Deployment | Existing Django/React web pipeline plus independent signed iOS/Android build and distribution pipelines |

Use compatible stable versions: R3F 9 pairs with the existing React 19 stack.
This route uses the web renderer inside Capacitor, not React Native or
`@react-three/fiber/native`. [R3F installation](https://r3f.docs.pmnd.rs/getting-started/installation).

Native releases package local built assets and use an explicit HTTPS API
origin. Production must not use a hosted website as Capacitor `server.url`;
that option is for development/live reload. Native UI runs in a WebView with
platform plugins. [Capacitor workflow](https://capacitorjs.com/docs/basics/workflow),
[configuration](https://capacitorjs.com/docs/config).

## Preservation and retirement rules

- Keep existing React routes, features, role variants, bookmarks, recovery paths
  and web PWA behavior usable throughout the work. `/play/` bookmarks resolve
  into the React pet collection after the old hosting router is removed.
- The scene is optional presentation. Model failure, WebGL loss or a disabled
  scene cannot prevent journal capture, pet actions, tasks, shopping or admin.
- Share API/services and UI components; do not create domain rules in the scene.
- Preserve family scoping and private journal/grade access. Use Django's local
  day policy rather than each phone's timezone.
- Identity and ownership are independent from artwork. Only confirmed receipts
  produce recognition; greetings and scenic interactions award nothing.
- A prototype is not full mobile parity. Promote the native app only after the
  complete feature/platform matrix passes.
- Retire Unity as an active client now, as authorized by the owner. Retain
  source, purchased inputs and historical operations docs for recovery. Do not
  delete licenses, original art, backups or shared API fixtures. React/Django
  fixture tests remain active. Do not imply that changing repository workflows
  has already stopped an independently running hosted service.

## Phases and effort

Initial estimates assume one experienced developer full time, reusing the UI
and owned assets. They exclude custom art, major gameplay and full offline
synchronization. Refine them after conversion and physical-device measurements;
source access, signing and external review can add elapsed time.

| Phase | Deliverable | Effort | Required result |
| --- | --- | --- | --- |
| 0 | Owned-asset R3F scene, usable React profile/pets and development Capacitor shell | 2–4 weeks | Art conversion and real-device feasibility proven |
| 1 | Production mobile shell, independent sessions and builds | 3–5 weeks | Concurrent native/browser use, restart/update and routing reliable |
| 2 | Full React functionality on native platforms | 4–7 weeks | All child/parent/staff workflows accepted |
| 3 | Complete asset-supported companion experience | 2–4 weeks | Ownership, mutations and visual acknowledgements preserved |
| 4 | Pilot and production iOS/Android/web releases | 2–4 weeks | Platform acceptance, recovery and store readiness |
| 5 | Optional asset-supported activities | Per approved slice | Available art and explicit behavior for each activity |

The core roadmap totals 13–24 engineering weeks, roughly 3–6 months. Phase 5
is optional and excluded. React remains the application on all three platforms.
The first implementation is the usable profile/pet slice, not all native
integrations or public mobile distribution.

## Phase 0 Start with the prototype and profile pets

Retrieve recorded archives/private backups; verify pack versions and applicable
licenses. Produce a private capability manifest and conversion pipeline for
Chick, Bird and a limited Forest Ruins subset. Validate textures, scale, facing,
skinning, clips and root motion before expanding. Never modify originals.
The asset review defines the license/public-delivery check; absent local
archives are not a reason to repurchase recorded owned art.

Reuse the complete React profile/customization and pet flows: selection,
feeding/evolution, hatching, breeding/cooldowns, expeditions/history/claims,
collection, inventory and Inbox. Add a shared lazy scene beside accessible DOM
controls. Exact Base Chick and confirmed Bird are the initial 3D bindings.
Fledgling is an explicitly labelled asset preview, never an earned stage.
Other species/variants retain their 2D art and acquisition paths. A greeting
uses a verified supplied clip or simple procedural motion and grants nothing.

Support loading/error/disabled states and the existing 2D presentation. Exclude
canvas gestures while sheets/controls own the interaction. Test keyboard,
safe-area resizing, density changes, reduced motion and scene entry/exit.

Create separate web/native profiles and development Capacitor projects for
iOS and Android using local packaged assets. Use synthetic staging accounts;
bundle no production accounts or secrets. Login still rotates the shared DRF
token, so isolated identities are required until Phase 1 device sessions exist.
Native boot must skip service-worker registration, PWA prompts/update banners
and browser Web Push initialization and teardown. Set explicit staging API
URLs, including sprite catalog calls. Complete URL/integration adaptation is
later work.

Exercise journal capture, navigation, media selection and one confirmed
companion/reward display in browser, iPhone Safari and installed native apps
on physical iPhone/Android hardware. Measure startup, frame time, memory,
battery/thermal behavior and repeated mounts; record budgets before expanding.
Demand rendering helps idle scenes; animation still needs frames.
[R3F performance](https://r3f.docs.pmnd.rs/advanced/scaling-performance).

**Exit gate:** owned creature and woodland subset render and animate correctly
on target phones and web; profile/pet actions and capture/navigation work with
the scene disabled or failing. Exact ownership, export metadata and measured
budgets are recorded. Missing hardware, private inputs or failed conversion
leave the gate incomplete; placeholders do not count as asset acceptance.

## Phase 1 Build the production foundation

Keep the Django-served web build/PWA. Native builds use local asset paths,
packaged fonts/models and an environment-bound HTTPS API origin. Centralize
trusted API/public/media URLs: the client supports `VITE_API_URL`, but catalog,
pagination, calendar/public URLs and links require auditing. Allow only selected
native CORS origins; test API and WebGL media separately. Generate workers,
install prompts and browser push only for web. Preserve web privacy-cache purge
and credential-bound identity checks; never cache private API responses in a
generic offline store. Native bundle updates use release management.

Introduce native device sessions alongside DRF Token authentication. Preserve
legacy responses and web rotation. Neither native nor web login may invalidate
the other client's independent session. Define device/all-device logout,
expiry/renewal, reset/deactivation/deletion revocation, including self-reset.
Bootstrap credentials asynchronously before authenticated requests. Renewable
credentials use reviewed secure storage, never Preferences/localStorage or a
persistent identity envelope. Keep the active credential in memory and bind
cached identity to a noncredential session identifier.

Add durable account/backend-scoped drafts, pending immutable payloads and save
UUIDs. Hydrate before recovery UI. Preferences is lightweight persistence;
media/large drafts need file/database storage, and credentials need secure
storage. Preserve web behavior and prevent cross-account recovery.
[Capacitor persistence](https://capacitorjs.com/docs/apis/preferences).

Before concurrent clients automatically present rewards, deploy stable event
IDs, explicit idempotent acknowledgements and inbox state separate from reveal
state. Preserve unseen events and prior consumption. Compatible Django/React
handling precedes another automatic consumer; Phase 3 is not the first safety
gate. Unity is retired and must not remain an automatic reward consumer.

Keep React Router; map verified Universal/App Links on cold launch, resume and
post-login return. Android back respects modal history and dirty-form guards
before navigation/exit. External links use a suitable browser without credentials.

Build signed apps from the same source revision as web, with real identifiers,
build numbers, protected signing material, configuration/source manifests,
symbols and crash reporting. Establish TestFlight/Play internal testing and
separate dev/staging/prod configurations. Obtain macOS/Xcode capacity. Mobile
distribution and backend/web deployment remain independently releasable.
Proposed API compatibility policy: at least 180 days after a client is replaced
by a generally available version, using additive evolution and update guidance.

**Exit gate:** browser/iOS/Android concurrently use one account. Restart/update
preserve drafts; reset/logout/switching and delayed responses recover safely.
Acknowledgement cannot clear unseen/later events. Routing/back/resume and web
regression pass. Signed internal builds cannot silently use production test data.

## Phase 2 Preserve every existing workflow on mobile

Build the matrix from actual routes, hub tabs, forms and API calls. Track each
role separately on web/iOS/Android. Reuse React screens and adapt services.

| Workflow | Native acceptance |
| --- | --- |
| Journal, grades, timeline, replies | Typing/dictation, durable drafts/UUIDs, conflict/midnight recovery, history/corrections, private/shared access |
| Tasks, homework, habits, movement, wellbeing | Proposals/proof/planning, submit/withdraw/approve/reject, schedules/caps/current earnings |
| Projects, templates, creations, gallery | Steps/milestones/collaboration/resources, photo/audio/imports, parent review, portfolio export |
| Time, money, savings, Coins, shop | Timers/timecards, decimals, distinct money/Coins, holds/refunds, stock/wishlist, exchanges, Greenlight manual/CSV |
| Pets, progression, profile | Full care/hatch/breed/expedition, inventory/consumables, skills/badges/cosmetics/settings; 2D remains valid |
| Printing | Links/uploads/previews/status, budgets/overrides, job linking, printer management |
| Family/staff | Account safeguards, templates/catalog/sprites, audit, OAuth admin, environment-gated dev tools |
| Integrations | Google sign-in/link/Calendar/Drive, media capture/files, downloads/sharing, notifications, legacy links |

Google authorization uses supported system authentication browsers and verified
return transactions. Replace credential-bearing callbacks with state/PKCE and
a short-lived single-use exchange while preserving web flow. Staff MCP OAuth
is not child/native login. [Google OAuth policy](https://developers.google.com/identity/protocols/oauth2/policies).

Retain web Drive Picker; define native equivalents before claiming parity,
including saved Drive-link resources, scopes/consent and server checks. An OS
Files import alone may not cover that journey. Test photo/audio/PDF/CSV/STL
inputs, multiple selection/cancellation/size/type checks and restoration after
Android activity/process interruption. Blob downloads (CSV/ZIP/ICS/QR) require
native filesystem/share/save behavior. Dictation needs a supported equivalent
or an explicitly accepted decision; hiding it is not parity.

Add account-bound native delivery through Django's notification chokepoint,
retaining web VAPID. Official Capacitor push returns APNs credentials on iOS
and FCM on Android: implement matching transports or deliberately select a
unified provider/plugin. Test denial, logout/switching, closed-app navigation.
[Capacitor push](https://capacitorjs.com/docs/apis/push-notifications).

Validate API/media CORS, expired private URLs, Sentry absolute-API tracing and
native symbols. The single printer listener retains MQTT ownership; phones
never connect directly. Public privacy/about, MCP and Django admin stay server
interfaces.

**Exit gate:** every role/workflow has native equivalents and web remains intact.
Create in mobile and approve/reply in browser, then reverse. Denial, offline,
process death, stale responses and updates recover. Hidden unsupported controls
or unauthenticated external-browser handoffs are not complete parity.

## Phase 3 Complete the companion experience

Connect the existing pet actions to shared R3F presentation on web/native.
Canvas clicks open accessible sheets; mutations use shared React/API services.
Retain uncertainty/reconciliation and exact identities/variants. Insufficient
3D coverage never removes an earned pet or acquisition path.

Ceremonies use available clips, overlays, reviewed effects and camera changes.
Do not require eating/breeding/hatching animation, fitted outfits or riding.
Archer is optional until required clips are verified. Stable source/event IDs,
read-only listing, idempotent acknowledgement and short-lived presenter claims
coordinate automatic reveals and recover from crashes. Keep inbox reads
separate. Adapt existing growth/drop/celebration consumers without inventing
old rewards. Showing before a crash may replay visuals; rewards occur once.

**Exit gate:** collection/actions work on all platforms; model failure leaves
working controls. Confirmed receipts, appearance bindings, interrupted committed
mutations, switching and reveal recovery pass. Animation creates no XP/Coins/items
and missing creatures are never replaced with the bird.

## Phase 4 Pilot and production release

Pilot physical phones, browser/PWA and native concurrently. Expand by cohort
after recorded crash/save/API/performance thresholds. Promote tested signed
builds; retain immutable web artifacts, symbols and exact source/config metadata.
Complete privacy/permission/review-access/family declarations and account removal.
Assess login alternatives/deletion requirements during Phase 1, preserving
family safeguards. [Apple review](https://developer.apple.com/app-store/review/guidelines/),
[Play review](https://support.google.com/googleplay/android-developer/answer/9859455).

Verify backups/restore drill, staging isolation, compatibility and rollback;
preserve Coolify deployment. Flags disable the scene without disabling forms
or losing pending drafts.

**Exit gate:** complete matrix accepted, physical-device lifecycle/accessibility/
performance passes, recovery exercised and submissions ready. Full offline sync
and new gameplay remain separate.

## Phase 5 Optional gameplay within the asset boundary

Choose small activities using existing art, such as scenery panels, bounded
paths with verified movement, an Archer guide or owned woodland arrangements.
These possibilities are not approved progression changes. Each slice names
exact meshes/clips/textures, ownership, local/server behavior, reward/anti-farm
rules, accessible alternatives and phone budgets. Fledgling progression,
decorating ownership, species/biomes, fitted clothes, combat and riding stay
outside baseline. Use 2D or defer missing art; do not require owner-made models.

**Exit gate:** dependencies verified, new saved/reward rules explicit and tested,
phone budgets pass and disabling the activity preserves ordinary workflows.

## Validation and recovery for every phase

Keep `npm run lint`, `npm run test:run`/coverage and `npm run build`. Run affected
Django permission/endpoint tests and PostgreSQL concurrency checks for
transaction changes. Update shared fixtures and active consumers together;
fixtures never replace permissions. Retained Unity source is reference only.

Add browser scene/lifecycle checks and packaged platform acceptance: cold boot,
remembered login, keyboard/safe areas/orientation, accessibility, slow/offline,
suspended/killed saves, switching, signed update and repeated mount/unmount.
Exercise WebGL loss/model failure and fallback. Simulators/screenshots do not
prove real-phone graphics readiness.

Flags preserve pending-save reconciliation and draft recovery. Installed bad
native bundles cannot be recalled: halt expansion, disable optional features
and issue a higher-version repair. A backend/SW deploy is not a native update.
Use deliberate current-main web/backend repairs, preserve compatibility and
never restart stale queued deployments. Record source, environment, supported
API/client range, model/artifact hashes, flags, measurements and recovery steps.

## First implementation checklist

- [ ] Retrieve sources/license records and verify Chick/Bird/Forest capabilities.
- [x] Produce private manifest and representative tested GLB exports.
- [x] Add lazy shared R3F profile/pet scene with complete DOM controls and 2D fallback.
- [x] Retire Unity navigation, CI/release dependencies and hosted route.
- [x] Create local development Capacitor profiles with trusted staging origin.
- [ ] Install on physical iPhone/Android and record art/keyboard/memory/lifecycle.
- [ ] Prove journal capture and confirmed receipt reaction with synthetic data.
- [ ] Accept measured budgets before expanding 3D scope.

The implementation record must distinguish completed repository work from
incomplete physical-device, hosting, session and distribution gates.
