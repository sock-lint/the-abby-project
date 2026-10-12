using System;
using System.Collections;
using System.Collections.Generic;
using AbbyCamp.Data;
using AbbyCamp.Presentation;
using AbbyCamp.Services;
using AbbyCamp.World;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace AbbyCamp.UI
{
    /// <summary>A fixed account home. Presentation never creates rewards or creature ownership.</summary>
    public sealed class CampPrototypeController : MonoBehaviour
    {
        [SerializeField] private CampGardenInput gardenInput;
        [SerializeField] private CompanionFollower companion;
        [SerializeField] private CampPresentationDefinition presentation;
        // Older private prepared scenes receive these only in the transient
        // build scene. Public scenes retain an empty array and no paid references.
        [SerializeField] private OwnedCreatureVisualBinding[] buildCreatureAppearances = Array.Empty<OwnedCreatureVisualBinding>();
        private enum Section { None, Rewards, Inbox, Bestiary, Account, Connect }
        private Section section;
        private AbbyApiClient api;
        private Font font;
        private Color ink = new Color(.286275f, .219608f, .309804f);
        private Color paper = new Color(1f, .972549f, .933333f);
        private Color teal = new Color(.458824f, .376471f, .658824f);
        private RectTransform canvas, safeArea, headingPanel, controlsPanel, footerPanel, toastPanel;
        private CampPhoneLayout phoneLayout;
        private Text titleLabel, modeLabel, coinsLabel, homeStatusLabel, companionNameLabel, companionHintLabel, toastLabel;
        private Button rewardsButton, inboxButton, bestiaryButton, patButton, journalButton, gradesButton, tasksButton, todayButton, connectButton;
        private Text rewardSummary, inboxSummary, bestiarySummary;
        private RectTransform modalSafeArea, modalSheet, modalFooter;
        private Text modalTitle, modalSubtitle;
        private ScrollRect modalScroll;
        private GameObject modal, lastFocusedInput;
        private bool revealFocusedInput;
        private CoinBalanceDto coins;
        private DropDto[] drops;
        private StableDto stable;
        private ExpeditionDto[] expeditions;
        private ExpeditionClaimDto expeditionClaim;
        private float expeditionsReadAt;
        private Text expeditionCountdownLabel;
        private InventoryEntryDto[] foodInventory, careInventory;
        private NotificationPageDto notifications;
        private UnreadCountDto unreadCount;
        private CharacterDto character;
        private MeadowDto meadow;
        private string homeStatus = "", rewardStatus = "", inboxStatus = "", bestiaryStatus = "";
        private bool busy, homeLoading, sectionLoading, markingRead, browserSessionDirty;
        private bool careInFlight, careDataReady, careReviewLoaded;
        private int selectedPetId, selectedFoodItemId, selectedEggItemId, selectedPotionItemId;
        private bool hatcheryOpen, expeditionsOpen;
        private int selectedExpeditionMountId, selectedExpeditionId;
        private string selectedExpeditionTier;
        private int sessionEpoch, viewVersion;
        private float nextHomeRefresh, toastUntil, patAvailableAt;
        private string inboxPageUrl;
        private readonly List<string> inboxHistory = new List<string>();
        private OwnedCompanionKind preferredCompanionKind;
        private int preferredCompanionId;
        private string companionChoiceScope;
        private OwnedCompanionChoice presentedCompanion = OwnedCompanionChoice.None;
        private OwnedCompanionChoice confirmedCompanion;

        public bool IsDemo => api == null || !api.IsAuthenticated;
        public bool IsModalOpen => modal != null;
        public bool IsBusy => busy || markingRead || careInFlight;
        public bool IsHomeLoading => homeLoading || busy || browserSessionDirty;
        public bool IsSectionLoading => sectionLoading;
        public string ActiveSection => section.ToString();
        public bool HatcheryOpen => section == Section.Bestiary && hatcheryOpen;
        public bool ExpeditionsOpen => section == Section.Bestiary && expeditionsOpen;
        public bool HasOwnedCompanionAppearance => companion != null && companion.HasOwnedAppearance;
        public OwnedCompanionChoice PresentedCompanion => presentedCompanion;
        public int DisplayedCreatureId => HasOwnedCompanionAppearance ? presentedCompanion.CreatureId : 0;
        public OwnedCompanionKind DisplayedCreatureKind => HasOwnedCompanionAppearance ? presentedCompanion.Kind : OwnedCompanionKind.None;
        public CampPresentationDefinition WorldPresentation => presentation;

        public void ConfigureBuildCreatureAppearances(OwnedCreatureVisualBinding[] bindings)
        {
            buildCreatureAppearances = bindings ?? Array.Empty<OwnedCreatureVisualBinding>();
        }
        // A credential-free, account-specific marker survives interrupted saves,
        // browser reloads and returning to an earlier account. It never replays a POST.
        private string CareReviewKey => IsDemo ? null : "abby:care:pending:" + Hash128.Compute(api.BaseUrl + "/" + api.CurrentUser.id);
        public bool CareNeedsReview => !IsDemo && PlayerPrefs.HasKey(CareReviewKey);
        private bool CanCare => !IsDemo && careDataReady && !CareNeedsReview && !IsBusy && !sectionLoading && !homeLoading;

        public void Configure(CampGardenInput input, CompanionFollower pet, CampPresentationDefinition worldPresentation = null)
        {
            gardenInput = input;
            companion = pet;
            presentation = worldPresentation;
        }

        private void Start()
        {
            if (gardenInput == null) gardenInput = FindFirstObjectByType<CampGardenInput>();
            if (companion == null) companion = FindFirstObjectByType<CompanionFollower>();
            api = GetComponent<AbbyApiClient>();
            if (api == null) api = gameObject.AddComponent<AbbyApiClient>();
            api.BrowserSessionChanged += BrowserSessionChanged;
            font = presentation != null && presentation.UiFont != null ? presentation.UiFont : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            if (presentation != null) { ink = presentation.Ink; paper = presentation.Paper; teal = presentation.Primary; }
            CreateInterface();
            if (gardenInput != null) gardenInput.CompanionTapped += PatCompanion;
            RefreshHud();
#if UNITY_WEBGL && !UNITY_EDITOR
            browserSessionDirty = true;
#endif
        }

        private void OnDestroy()
        {
            if (api != null) api.BrowserSessionChanged -= BrowserSessionChanged;
            if (gardenInput != null) gardenInput.CompanionTapped -= PatCompanion;
            if (phoneLayout != null) phoneLayout.LayoutChanged -= LayoutInterface;
        }

        private void Update()
        {
            if (canvas == null) return;
            if (browserSessionDirty && !busy && !api.SessionTransitionInFlight)
            {
                browserSessionDirty = false;
                StartCoroutine(ConnectBrowserSession());
            }
            if (!IsDemo && !homeLoading && !sectionLoading && !IsBusy && !IsModalOpen && Time.unscaledTime >= nextHomeRefresh)
                StartCoroutine(RefreshHome());
            foreach (var button in new[] { rewardsButton, inboxButton, bestiaryButton, patButton, journalButton, gradesButton, tasksButton, todayButton, connectButton })
                button.interactable = !IsBusy && !IsModalOpen;
            if (IsModalOpen && Input.GetKeyDown(KeyCode.Escape) && !IsBusy) CloseModal();
#if UNITY_EDITOR || DEVELOPMENT_BUILD
            if (!IsModalOpen && Input.GetKeyDown(KeyCode.K)) companion?.ToggleAppearance();
#endif
            if (Time.unscaledTime > toastUntil) toastPanel.gameObject.SetActive(false);
            if (ExpeditionsOpen && expeditionCountdownLabel != null)
            {
                var trip = FindExpedition(selectedExpeditionId);
                if (trip != null) expeditionCountdownLabel.text = ExpeditionCountdown(trip);
            }
            KeepFocusedInputVisible();
        }

        private void OnApplicationFocus(bool focused) { if (focused) nextHomeRefresh = 0; }

        private bool Current(int epoch) => epoch == sessionEpoch && !IsDemo;

        private void ClearPresentation()
        {
            sessionEpoch++;
            preferredCompanionKind = OwnedCompanionKind.None; preferredCompanionId = 0; companionChoiceScope = null;
            confirmedCompanion = null; presentedCompanion = OwnedCompanionChoice.None;
            companion?.ClearOwnedAppearance(true);
            coins = null; drops = null; stable = null; notifications = null; unreadCount = null; character = null; meadow = null;
            foodInventory = careInventory = null;
            expeditions = null; expeditionClaim = null; expeditionCountdownLabel = null;
            selectedExpeditionMountId = selectedExpeditionId = 0; selectedExpeditionTier = null;
            expeditionsOpen = false;
            selectedPetId = selectedFoodItemId = selectedEggItemId = selectedPotionItemId = 0;
            hatcheryOpen = false;
            careInFlight = careDataReady = careReviewLoaded = false;
            homeStatus = rewardStatus = inboxStatus = bestiaryStatus = "";
            inboxPageUrl = null; inboxHistory.Clear();
            busy = homeLoading = sectionLoading = markingRead = false;
            nextHomeRefresh = 0;
            if (toastPanel != null) toastPanel.gameObject.SetActive(false);
            DismissModal();
            RefreshHud();
        }

        private void BrowserSessionChanged()
        {
            ClearPresentation();
            browserSessionDirty = true;
        }

        private IEnumerator ConnectBrowserSession()
        {
            var epoch = sessionEpoch;
            busy = true;
            ApiError failure = null;
            yield return api.ResumeBrowserSession(_ => { }, error => failure = error);
            if (epoch != sessionEpoch) yield break;
            busy = false;
            RefreshHud();
            if (failure != null) { Toast(failure.Message, 7); yield break; }
            yield return RefreshHome();
        }

        private IEnumerator RefreshHome()
        {
            if (IsDemo || homeLoading) yield break;
            var epoch = sessionEpoch;
            homeLoading = true;
            nextHomeRefresh = Time.unscaledTime + 30;
            homeStatus = "Updating your progress…";
            RefreshHud();
            ApiError failure = null;
            CoinBalanceDto loadedCoins = null;
            UnreadCountDto loadedUnread = null;
            StableDto loadedStable = null;
            CharacterDto loadedCharacter = null;
            try
            {
                yield return api.FetchCoins(value => loadedCoins = value, error => failure = error);
                if (!Current(epoch)) yield break;
                if (loadedCoins != null) coins = loadedCoins;
                yield return api.FetchUnreadNotificationCount(value => loadedUnread = value, error => failure = error);
                if (!Current(epoch)) yield break;
                if (loadedUnread != null) unreadCount = loadedUnread;
                yield return api.FetchStable(value => loadedStable = value, error => failure = error);
                if (!Current(epoch)) yield break;
                if (loadedStable != null) AcceptStable(loadedStable);
                yield return api.FetchCharacter(value => loadedCharacter = value, error => failure = error);
                if (!Current(epoch)) yield break;
                if (loadedCharacter != null) character = loadedCharacter;
                homeStatus = failure == null ? "" : "Refresh unavailable · Open a section to retry";
            }
            finally
            {
                if (epoch == sessionEpoch)
                {
                    homeLoading = false;
                    if (IsDemo) ClearPresentation();
                    else
                    {
                        RefreshHud();
                        if ((section == Section.Inbox || section == Section.Bestiary) && !sectionLoading && !IsBusy) DrawActiveSection();
                    }
                }
            }
        }

        private void CreateInterface()
        {
            var go = new GameObject("PlayInterface", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            go.transform.SetParent(transform, false);
            go.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
            canvas = go.GetComponent<RectTransform>();
            safeArea = Box(canvas, "CampSafeArea", Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            safeArea.anchorMax = Vector2.one;
            phoneLayout = go.AddComponent<CampPhoneLayout>();
            phoneLayout.Configure(go.GetComponent<Canvas>(), go.GetComponent<CanvasScaler>(), safeArea);
            if (FindFirstObjectByType<EventSystem>() == null) new GameObject("CampEventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
            headingPanel = Panel(safeArea, "PlayHeading", Vector2.zero, Vector2.up, Vector2.up, Vector2.zero, paper);
            titleLabel = Label(headingPanel, "Play", 30, Vector2.zero, Vector2.zero, TextAnchor.UpperLeft, ink);
            titleLabel.name = "CampTitle";
            titleLabel.verticalOverflow = VerticalWrapMode.Overflow;
            modeLabel = Label(headingPanel, "", 15, Vector2.zero, Vector2.zero, TextAnchor.UpperLeft, ink); modeLabel.name = "AccountMode";
            coinsLabel = Label(headingPanel, "", 15, Vector2.zero, Vector2.zero, TextAnchor.UpperLeft, ink); coinsLabel.name = "CoinsBalance";
            homeStatusLabel = Label(headingPanel, "", 13, Vector2.zero, Vector2.zero, TextAnchor.UpperLeft, ink); homeStatusLabel.name = "HomeStatus";
            homeStatusLabel.verticalOverflow = VerticalWrapMode.Overflow;
            connectButton = Button(headingPanel, "Connect", Vector2.zero, Vector2.zero, OpenConnection, true); connectButton.name = "AccountButton";
            todayButton = Button(headingPanel, "Today", Vector2.zero, Vector2.zero, () => Navigate(PlayDestination.Today), true); todayButton.name = "TodayButton";
            controlsPanel = Panel(safeArea, "PlayActions", Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero, paper);
            rewardsButton = HomeCard("RewardsButton", "Rewards", out rewardSummary, OpenRewards);
            inboxButton = HomeCard("InboxButton", "Inbox", out inboxSummary, OpenInbox); inboxSummary.name = "UnreadCount";
            bestiaryButton = HomeCard("BestiaryButton", "Pets", out bestiarySummary, OpenBestiary);
            journalButton = Button(controlsPanel, "Journal", Vector2.zero, Vector2.zero, () => Navigate(PlayDestination.Journal), true); journalButton.name = "JournalButton";
            gradesButton = Button(controlsPanel, "Grades", Vector2.zero, Vector2.zero, () => Navigate(PlayDestination.Grades), true); gradesButton.name = "GradesButton";
            tasksButton = Button(controlsPanel, "Tasks", Vector2.zero, Vector2.zero, () => Navigate(PlayDestination.Tasks), true); tasksButton.name = "TasksButton";
            footerPanel = Panel(safeArea, "CompanionGreeting", Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero, paper);
            companionNameLabel = Label(footerPanel, "Meadow friend", 20, Vector2.zero, Vector2.zero, TextAnchor.MiddleLeft, ink); companionNameLabel.name = "CompanionName";
            companionHintLabel = Label(footerPanel, "Artwork preview", 13, Vector2.zero, Vector2.zero, TextAnchor.MiddleLeft, ink);
            patButton = Button(footerPanel, "Say hello", Vector2.zero, Vector2.zero, PatCompanion); patButton.name = "PatCompanionButton";
            toastPanel = Panel(safeArea, "PlayToast", Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero, paper);
            toastLabel = Label(toastPanel, "", 14, Vector2.zero, Vector2.zero, TextAnchor.MiddleCenter, ink); toastLabel.name = "CampMessage";
            toastPanel.gameObject.SetActive(false);
            phoneLayout.LayoutChanged += LayoutInterface;
            LayoutInterface();
        }

        private Button HomeCard(string name, string title, out Text summary, Action clicked)
        {
            var button = Button(controlsPanel, title, Vector2.zero, Vector2.zero, clicked, true);
            button.name = name;
            var heading = button.GetComponentInChildren<Text>();
            heading.fontSize = 18;
            heading.alignment = TextAnchor.MiddleCenter;
            heading.color = ink;
            summary = Label(button.transform, "", 12, Vector2.zero, Vector2.zero, TextAnchor.MiddleCenter, ink);
            summary.verticalOverflow = VerticalWrapMode.Overflow;
            return button;
        }

        public void PatCompanion()
        {
            if (IsBusy || IsModalOpen || companion == null || Time.unscaledTime < patAvailableAt) return;
            patAvailableAt = Time.unscaledTime + .8f;
            companion.Celebrate();
            Toast("Your meadow friend is happy to see you!");
        }

        private void Navigate(PlayDestination destination)
        {
            if (!api.OpenDestination(destination)) Toast("Open this section in the web app.");
        }

        private void RefreshHud()
        {
            if (modeLabel == null) return;
            modeLabel.text = IsDemo ? "Sign in to see your progress" : Shorten(api.CurrentUser.DisplayName, 34);
            connectButton.GetComponentInChildren<Text>().text = IsDemo ? "Connect" : "Account";
            coinsLabel.text = IsDemo ? "A little place for your companion" : coins == null ? "Loading coins…" : coins.balance.ToString("N0") + " coins" + (character == null ? "" : "  ·  Level " + character.level);
            homeStatusLabel.text = homeStatus;
            rewardSummary.text = IsDemo ? "Your progress" : coins == null ? "Loading…" : coins.balance.ToString("N0") + " coins";
            inboxSummary.text = IsDemo ? "Your updates" : unreadCount == null ? "Loading…" : unreadCount.count + " unread";
            bestiarySummary.text = IsDemo ? "Your pets" : stable == null ? "Loading…" : stable.total_pets + " pets · " + stable.total_mounts + " mounts";
            RefreshCompanionPresentation();
        }

        private void AcceptStable(StableDto value)
        {
            stable = value;
            confirmedCompanion = null;
            RefreshCompanionPresentation();
        }

        private void LoadCompanionPreference()
        {
            if (IsDemo) return;
            string scope = "abby:companion:choice:" + Hash128.Compute(api.BaseUrl + "/" + api.CurrentUser.id);
            if (scope == companionChoiceScope) return;
            companionChoiceScope = scope;
            preferredCompanionKind = (OwnedCompanionKind)PlayerPrefs.GetInt(scope + ":kind", 0);
            preferredCompanionId = PlayerPrefs.GetInt(scope + ":id", 0);
        }

        private void RememberCompanion(OwnedCompanionChoice choice)
        {
            if (IsDemo || choice == null || choice.Kind == OwnedCompanionKind.None) return;
            LoadCompanionPreference();
            preferredCompanionKind = choice.Kind; preferredCompanionId = choice.CreatureId;
            PlayerPrefs.SetInt(companionChoiceScope + ":kind", (int)choice.Kind);
            PlayerPrefs.SetInt(companionChoiceScope + ":id", choice.CreatureId);
            PlayerPrefs.Save();
            confirmedCompanion = choice;
            RefreshCompanionPresentation();
        }

        private void RefreshCompanionPresentation()
        {
            if (IsDemo)
            {
                presentedCompanion = OwnedCompanionChoice.None;
                companion?.ClearOwnedAppearance();
            }
            else
            {
                LoadCompanionPreference();
                presentedCompanion = confirmedCompanion ?? OwnedCompanionResolver.Resolve(stable, preferredCompanionKind, preferredCompanionId);
                VisualDefinition definition = null;
                bool mapped = presentedCompanion.Kind != OwnedCompanionKind.None && presentation != null
                    && presentation.TryResolveOwnedAppearance(presentedCompanion.Species.sprite_key, presentedCompanion.Potion.slug,
                        presentedCompanion.IsEvolved, out definition);
                if (!mapped && presentedCompanion.Kind != OwnedCompanionKind.None)
                    mapped = OwnedCreatureVisualBinding.TryResolve(buildCreatureAppearances, presentedCompanion.Species.sprite_key,
                        presentedCompanion.Potion.slug, presentedCompanion.IsEvolved, out definition);
                if (mapped) companion?.SetOwnedAppearance(definition);
                else companion?.ClearOwnedAppearance();
            }
            if (companionNameLabel == null) return;
            companionNameLabel.text = HasOwnedCompanionAppearance ? presentedCompanion.DisplayName : "Meadow friend";
            companionHintLabel.text = HasOwnedCompanionAppearance
                ? presentedCompanion.IsEvolved ? presentedCompanion.Kind == OwnedCompanionKind.Mount ? "Your mount" : "Your evolved companion"
                    : "Your companion · " + presentedCompanion.Growth + " / 100 growth"
                : presentedCompanion.Kind == OwnedCompanionKind.None ? "Artwork preview"
                    : "Artwork preview · " + presentedCompanion.Species.name + " model unavailable";
        }

        public void OpenRewards() => OpenSection(Section.Rewards);
        public void OpenInbox() => OpenSection(Section.Inbox);
        public void OpenBestiary()
        {
            if (IsBusy) return;
            selectedPetId = selectedFoodItemId = selectedEggItemId = selectedPotionItemId = 0;
            hatcheryOpen = false;
            expeditionsOpen = false; selectedExpeditionMountId = selectedExpeditionId = 0;
            selectedExpeditionTier = null; expeditionClaim = null;
            OpenSection(Section.Bestiary);
        }

        private void OpenSection(Section target)
        {
            if (IsBusy) return;
            section = target;
            viewVersion++;
            sectionLoading = false;
            DrawActiveSection(true);
            if (!IsDemo) StartCoroutine(LoadSection(target));
        }

        private IEnumerator LoadSection(Section target)
        {
            if (IsDemo || sectionLoading || IsBusy) yield break;
            var epoch = sessionEpoch;
            var view = viewVersion;
            sectionLoading = true;
            if (target == Section.Bestiary)
            {
                careDataReady = careReviewLoaded = false;
                selectedEggItemId = selectedPotionItemId = 0;
                selectedExpeditionTier = null;
            }
            SetSectionStatus(target, "Refreshing…");
            DrawActiveSection();
            ApiError failure = null;
            bool Valid() => Current(epoch) && view == viewVersion && section == target;
            try
            {
                if (target == Section.Rewards)
                {
                    CoinBalanceDto loadedCoins = null;
                    DropDto[] loadedDrops = null;
                    MeadowDto loadedMeadow = null;
                    yield return api.FetchCoins(value => loadedCoins = value, error => failure = error);
                    if (!Valid()) yield break;
                    if (loadedCoins != null) coins = loadedCoins;
                    yield return api.FetchRecentDrops(value => loadedDrops = value, error => failure = error);
                    if (!Valid()) yield break;
                    if (loadedDrops != null) drops = loadedDrops;
                    yield return api.FetchMeadow(value => loadedMeadow = value, error => failure = error);
                    if (!Valid()) yield break;
                    if (loadedMeadow != null)
                    {
                        meadow = loadedMeadow;
                        var unseen = MeadowReceiptMemory.Observe(api.BaseUrl, api.CurrentUser.id, meadow);
                        if (unseen != null) { companion?.Celebrate(); Toast("A new memory bloom joined your rewards.", 7); }
                    }
                }
                else if (target == Section.Inbox)
                {
                    NotificationPageDto loadedPage = null;
                    UnreadCountDto loadedCount = null;
                    yield return api.FetchNotifications(value => loadedPage = value, error => failure = error, inboxPageUrl);
                    if (!Valid()) yield break;
                    if (loadedPage != null) notifications = loadedPage;
                    yield return api.FetchUnreadNotificationCount(value => loadedCount = value, error => failure = error);
                    if (!Valid()) yield break;
                    if (loadedCount != null) unreadCount = loadedCount;
                }
                else if (target == Section.Bestiary)
                {
                    StableDto loaded = null;
                    InventoryEntryDto[] loadedItems = null;
                    ExpeditionDto[] loadedTrips = null;
                    CoinBalanceDto loadedCoins = null;
                    yield return api.FetchStable(value => loaded = value, error => failure = error);
                    if (!Valid()) yield break;
                    if (loaded != null) AcceptStable(loaded);
                    yield return api.FetchCareInventory(value => loadedItems = value, error => failure = error);
                    if (!Valid()) yield break;
                    careInventory = loadedItems;
                    foodInventory = CareSupplies("food");
                    yield return api.FetchExpeditions(value => loadedTrips = value, error => failure = error);
                    if (!Valid()) yield break;
                    expeditions = loadedTrips; expeditionsReadAt = Time.unscaledTime;
                    yield return api.FetchCoins(value => loadedCoins = value, error => failure = error);
                    if (!Valid()) yield break;
                    if (loadedCoins != null) coins = loadedCoins;
                    careDataReady = careReviewLoaded = failure == null && loaded != null && loadedItems != null && loadedTrips != null && loadedCoins != null;
                }
                if (Valid()) SetSectionStatus(target, failure == null ? "Up to date" : failure.Message + " Try Refresh.");
            }
            finally
            {
                if (epoch == sessionEpoch && view == viewVersion)
                {
                    sectionLoading = false;
                    if (IsDemo) ClearPresentation();
                    else { RefreshHud(); DrawActiveSection(); }
                }
            }
        }

        private void SetSectionStatus(Section target, string value)
        {
            if (target == Section.Rewards) rewardStatus = value;
            else if (target == Section.Inbox) inboxStatus = value;
            else if (target == Section.Bestiary) bestiaryStatus = value;
        }

        private void DrawActiveSection(bool resetScroll = false)
        {
            // ScrollRect can report zero for a short, top-aligned loading sheet.
            // Preserve the top when data makes that sheet taller than its viewport.
            var scroll = resetScroll || modalScroll == null
                || modalScroll.content.rect.height <= modalScroll.viewport.rect.height + 1f
                ? 1 : modalScroll.verticalNormalizedPosition;
            switch (section)
            {
                case Section.Rewards: DrawRewards(); break;
                case Section.Inbox: DrawInbox(); break;
                case Section.Bestiary: DrawBestiary(); break;
                default: return;
            }
            LayoutInterface();
            Canvas.ForceUpdateCanvases();
            modalScroll.StopMovement();
            modalScroll.verticalNormalizedPosition = scroll;
        }

        private void DemoMessage(RectTransform content)
        {
            FlowLabel(content, "ConnectPrompt", "Connect your account to see your saved progress and creature collection.", 17, ink);
            FlowButton(content, "SectionConnectButton", "Connect your account", OpenConnection);
        }

        private void SectionFooter(Section target)
        {
            FooterButton("Refresh" + target + "Button", "Refresh", () => StartCoroutine(LoadSection(target))).interactable = !IsDemo && !sectionLoading && !IsBusy;
            FooterButton("Close" + target + "Button", "Close", CloseModal).interactable = !IsBusy;
        }

        private void DrawRewards()
        {
            BeginModal("Rewards", "Look at what you've earned.");
            var content = modalScroll.content;
            if (IsDemo) DemoMessage(content);
            else
            {
                FlowLabel(content, "RewardStatus", rewardStatus, 14, ink);
                FlowLabel(content, "RewardBalance", coins == null ? "Loading your balance…" : coins.balance.ToString("N0") + " coins", 26, ink);
                FlowButton(content, "RewardShopButton", "Open reward shop", () => Navigate(PlayDestination.RewardShop));
                FlowButton(content, "SatchelButton", "Open inventory", () => Navigate(PlayDestination.Satchel));
                FlowLabel(content, "CoinHistoryHeading", "Recent coin activity", 19, ink);
                if (coins != null && coins.recent_transactions.Length == 0) FlowLabel(content, "EmptyCoinHistory", "Your earned coins will appear here.", 16, ink);
                if (coins != null) foreach (var item in coins.recent_transactions)
                {
                    var row = Row(content, "Coin_" + item.id);
                    FlowLabel(row, "CoinAmount", (item.amount > 0 ? "+" : "") + item.amount + " coins", 18, ink);
                    FlowLabel(row, "CoinDescription", string.IsNullOrWhiteSpace(item.description) ? Humanize(item.reason) : item.description, 16, ink);
                    FlowLabel(row, "CoinDate", Date(item.created_at), 13, ink);
                }
                FlowLabel(content, "DropHistoryHeading", "Recently earned items", 19, ink);
                if (drops == null) FlowLabel(content, "LoadingDrops", "Loading your items…", 16, ink);
                else if (drops.Length == 0) FlowLabel(content, "EmptyDrops", "New items will appear here as you earn them.", 16, ink);
                else foreach (var item in drops)
                {
                    var row = Row(content, "Drop_" + item.id);
                    FlowLabel(row, "DropName", item.item_name + (item.quantity > 1 ? " × " + item.quantity : ""), 18, ink);
                    FlowLabel(row, "DropDetail", item.was_salvaged ? "Converted to coins · " + Date(item.created_at) : "Already added to your items · " + Date(item.created_at), 14, ink);
                }
                if (meadow != null)
                {
                    FlowLabel(content, "KeepsakeCount", meadow.keepsake_count + " memory blooms · " + meadow.journal_xp_awarded + " journal XP", 19, ink);
                    foreach (var item in meadow.keepsakes)
                    {
                        var row = Row(content, "Keepsake_" + item.receipt_id);
                        FlowLabel(row, "KeepsakeTitle", item.title, 17, ink);
                        FlowLabel(row, "KeepsakeDate", Date(item.earned_at), 14, ink);
                    }
                }
                FlowLabel(content, "RewardExplanation", "These rewards are already part of your account. Your journal words stay in your journal.", 14, ink);
            }
            SectionFooter(Section.Rewards);
        }

        private void DrawInbox()
        {
            BeginModal("Inbox", "Task, reward, and pet updates.");
            var content = modalScroll.content;
            if (IsDemo) DemoMessage(content);
            else
            {
                FlowLabel(content, "InboxStatus", markingRead ? "Saving read status…" : inboxStatus, 14, ink);
                FlowLabel(content, "InboxUnreadCount", unreadCount == null ? "Loading unread count…" : unreadCount.count + " unread updates", 20, ink);
                if (notifications == null) FlowLabel(content, "LoadingInbox", sectionLoading ? "Loading your updates…" : "Your updates couldn't load. Try Refresh.", 16, ink);
                else if (notifications.results.Length == 0) FlowLabel(content, "EmptyInbox", "You're all caught up. New updates will appear here.", 17, ink);
                else foreach (var item in notifications.results)
                {
                    var row = Row(content, "Notification_" + item.id);
                    FlowLabel(row, "NotificationTitle_" + item.id, (item.is_read ? "" : "New · ") + item.title, 18, ink);
                    FlowLabel(row, "NotificationMessage_" + item.id, item.message, 16, ink);
                    FlowLabel(row, "NotificationDate", Date(item.created_at) + (item.is_read ? " · Read" : " · Unread"), 13, ink);
                    var hasDestination = AbbyApiClient.TryResolveNotificationDestination(item.link, item.notification_type, out _);
                    FlowButton(row, "OpenNotification_" + item.id, hasDestination ? "Open related page" : "Open Today", () =>
                    {
                        if (!api.OpenNotificationDestination(item)) Navigate(PlayDestination.Today);
                    }).interactable = !markingRead;
                    var mark = FlowButton(row, "MarkRead_" + item.id, item.is_read ? "Read" : "Mark read", () => StartCoroutine(MarkRead(item.id)));
                    mark.interactable = !item.is_read && !markingRead && !sectionLoading && !homeLoading;
                }
                if (inboxHistory.Count > 0) FlowButton(content, "PreviousInboxPageButton", "Previous page", () =>
                {
                    inboxPageUrl = inboxHistory[inboxHistory.Count - 1]; inboxHistory.RemoveAt(inboxHistory.Count - 1);
                    notifications = null; DrawActiveSection(true); StartCoroutine(LoadSection(Section.Inbox));
                }).interactable = !sectionLoading && !markingRead;
                if (notifications != null && !string.IsNullOrEmpty(notifications.next)) FlowButton(content, "NextInboxPageButton", "Next page", () =>
                {
                    inboxHistory.Add(inboxPageUrl); inboxPageUrl = notifications.next;
                    notifications = null; DrawActiveSection(true); StartCoroutine(LoadSection(Section.Inbox));
                }).interactable = !sectionLoading && !markingRead;
            }
            SectionFooter(Section.Inbox);
        }

        private IEnumerator MarkRead(int id)
        {
            if (IsDemo || markingRead || sectionLoading || homeLoading) yield break;
            var epoch = sessionEpoch;
            var view = viewVersion;
            markingRead = true;
            DrawActiveSection();
            ApiError failure = null;
            NotificationDto saved = null;
            try
            {
                yield return api.MarkNotificationRead(id, value => saved = value, error => failure = error);
                if (!Current(epoch) || view != viewVersion) yield break;
                if (saved != null)
                {
                    if (notifications != null) for (int i = 0; i < notifications.results.Length; i++) if (notifications.results[i].id == id) notifications.results[i] = saved;
                    unreadCount = null;
                    yield return api.FetchUnreadNotificationCount(value => unreadCount = value, error => failure = error);
                    if (!Current(epoch) || view != viewVersion) yield break;
                }
                inboxStatus = failure == null ? "Read status saved" : saved != null
                    ? "Read status saved. Refresh to update the unread count."
                    : "Couldn't confirm the read status. Refresh or try Mark read again.";
            }
            finally
            {
                if (epoch == sessionEpoch && view == viewVersion)
                {
                    markingRead = false;
                    if (IsDemo) ClearPresentation();
                    else { RefreshHud(); DrawActiveSection(); }
                }
            }
        }

        private void DrawBestiary()
        {
            expeditionCountdownLabel = null;
            if (expeditionsOpen) { DrawExpeditions(); return; }
            if (hatcheryOpen) { DrawHatchery(); return; }
            if (selectedPetId != 0) { DrawPetCare(); return; }
            BeginModal("Pets", "Your companions and mounts.");
            var content = modalScroll.content;
            if (IsDemo) DemoMessage(content);
            else
            {
                FlowLabel(content, "BestiaryStatus", bestiaryStatus, 14, ink);
                DrawCareReview(content);
                if (stable == null) FlowLabel(content, "LoadingStable", "Opening your creatures…", 16, ink);
                else
                {
                    FlowLabel(content, "StableCounts", stable.total_pets + " pets · " + stable.total_mounts + " mounts", 22, ink);
                    FlowButton(content, "ExpeditionsButton", "Mount expeditions", () => OpenExpeditions(0, 0)).interactable = !IsBusy && !sectionLoading;
                    FlowLabel(content, "ActiveCompanion", stable.ActiveCompanion == null ? "No active companion yet" : "Active companion: " + PetName(stable.ActiveCompanion), 18, ink);
                    FlowLabel(content, "CompanionArtNote", HasOwnedCompanionAppearance
                        ? "The scene shows your selected " + (presentedCompanion.IsEvolved ? "grown creature" : "companion") + "."
                        : "The scene is an artwork preview. A matching owned creature and its prepared model are required.", 14, ink);
                    FlowLabel(content, "PetsHeading", "Companions", 19, ink);
                    if (stable.pets.Length == 0) FlowLabel(content, "EmptyPets", "Your first companion is waiting to be discovered.", 16, ink);
                    foreach (var pet in stable.pets)
                    {
                        var row = Row(content, "Pet_" + pet.id);
                        FlowLabel(row, "PetName_" + pet.id, PetName(pet) + (pet.is_active ? " · Active" : ""), 18, ink);
                        FlowLabel(row, "PetSpecies", pet.potion.name + " " + pet.species.name, 16, ink);
                        FlowLabel(row, "PetGrowth", pet.evolved_to_mount ? "Evolved into a mount" : pet.is_fully_grown ? "Fully grown" : pet.growth_points + " growth", 14, ink);
                        FlowLabel(row, "PetHappiness", Humanize(pet.happiness_level), 14, ink);
                        if (!pet.evolved_to_mount)
                        {
                            FlowButton(row, "FeedPet_" + pet.id, "Feed " + PetName(pet), () =>
                            {
                                selectedPetId = pet.id; selectedFoodItemId = 0; DrawActiveSection(true);
                            }).interactable = CanCare;
                            if (!pet.is_active || presentedCompanion.Kind != OwnedCompanionKind.Pet || presentedCompanion.CreatureId != pet.id)
                                FlowButton(row, "ActivePet_" + pet.id, "Choose as companion", () => StartCoroutine(SaveCare(pet.id, 0, false))).interactable = CanCare;
                        }
                    }
                    FlowLabel(content, "MountsHeading", "Mounts", 19, ink);
                    if (stable.mounts.Length == 0) FlowLabel(content, "EmptyMounts", "Your mounts will appear here as your collection grows.", 16, ink);
                    foreach (var mount in stable.mounts)
                    {
                        var row = Row(content, "Mount_" + mount.id);
                        FlowLabel(row, "MountName", mount.potion.name + " " + mount.species.name + (mount.is_active ? " · Active" : ""), 18, ink);
                        DrawMountExpedition(row, mount);
                        if (!mount.is_active || presentedCompanion.Kind != OwnedCompanionKind.Mount || presentedCompanion.CreatureId != mount.id)
                            FlowButton(row, "ActiveMount_" + mount.id, "Choose as mount", () => StartCoroutine(SaveCare(mount.id, 0, true))).interactable = CanCare && mount.active_expedition == null;
                    }
                }
                FlowButton(content, "CompanionsWebButton", "View companions", () => Navigate(PlayDestination.BestiaryCompanions)).interactable = !IsBusy;
                FlowButton(content, "MountsWebButton", "View mounts and breeding", () => Navigate(PlayDestination.BestiaryMounts)).interactable = !IsBusy;
                FlowButton(content, "HatcheryButton", "Hatch a companion", () =>
                {
                    hatcheryOpen = true; expeditionsOpen = false; selectedPetId = selectedFoodItemId = selectedEggItemId = selectedPotionItemId = 0;
                    DrawActiveSection(true);
                }).interactable = !IsBusy && !sectionLoading;
                FlowButton(content, "HatcheryWebButton", "Open hatching", () => Navigate(PlayDestination.BestiaryHatchery)).interactable = !IsBusy;
                FlowButton(content, "SpeciesWebButton", "Discover species", () => Navigate(PlayDestination.BestiaryCodex));
            }
            SectionFooter(Section.Bestiary);
        }

        private void OpenExpeditions(int mountId, int expeditionId)
        {
            if (IsBusy) return;
            expeditionsOpen = true; hatcheryOpen = false;
            selectedPetId = selectedFoodItemId = selectedEggItemId = selectedPotionItemId = 0;
            if (selectedExpeditionId != expeditionId) expeditionClaim = null;
            selectedExpeditionMountId = mountId; selectedExpeditionId = expeditionId;
            selectedExpeditionTier = null;
            DrawActiveSection(true);
        }

        private ExpeditionDto FindExpedition(int id) => expeditions == null ? null : Array.Find(expeditions, trip => trip.id == id);
        private OwnedMountDto FindMount(int id) => stable?.mounts == null ? null : Array.Find(stable.mounts, mount => mount.id == id);

        private void DrawMountExpedition(RectTransform row, OwnedMountDto mount)
        {
            if (mount.active_expedition != null)
            {
                int id = mount.active_expedition.id;
                var trip = FindExpedition(id);
                FlowLabel(row, "ExpeditionStatus_" + id, trip != null && trip.CanClaim ? "Ready to claim" : "Out exploring", 16, ink);
                FlowButton(row, "ViewExpedition_" + id, "View expedition", () => OpenExpeditions(mount.id, id)).interactable = !IsBusy && !sectionLoading;
            }
            else
            {
                FlowButton(row, "ExpeditionMount_" + mount.id, "Plan expedition", () => OpenExpeditions(mount.id, 0)).interactable = !IsBusy && !sectionLoading;
                var previous = expeditions == null ? null : Array.Find(expeditions, trip => trip.mount_id == mount.id);
                if (previous != null)
                {
                    int id = previous.id;
                    FlowButton(row, "ViewExpedition_" + id, "View last expedition", () => OpenExpeditions(mount.id, id)).interactable = !IsBusy && !sectionLoading;
                }
            }
        }

        private void DrawExpeditions()
        {
            var mount = FindMount(selectedExpeditionMountId);
            BeginModal("Mount expeditions", mount == null ? "Send a mount exploring and collect its saved finds." : mount.potion.name + " " + mount.species.name);
            var content = modalScroll.content;
            FlowLabel(content, "BestiaryStatus", bestiaryStatus, 14, ink);
            DrawCareReview(content);
            if (selectedExpeditionMountId == 0)
            {
                FlowLabel(content, "ExpeditionExplanation", "Your mounts keep exploring while Play is closed. Each mount can take one trip per day; return here to claim its finds.", 16, ink);
                if (stable?.mounts == null) FlowLabel(content, "ExpeditionLoadingMounts", "Refresh to load your mounts.", 16, ink);
                else if (stable.mounts.Length == 0) FlowLabel(content, "ExpeditionEmptyMounts", "Your mounts will appear here as your collection grows.", 16, ink);
                else foreach (var owned in stable.mounts)
                {
                    var row = Row(content, "ExpeditionMountRow_" + owned.id);
                    FlowLabel(row, "ExpeditionMountName_" + owned.id, owned.potion.name + " " + owned.species.name + (owned.is_active ? " · Active" : ""), 18, ink);
                    DrawMountExpedition(row, owned);
                }
                FlowButton(content, "BackExpeditionCollectionButton", "Back to pets", () =>
                {
                    expeditionsOpen = false; selectedExpeditionMountId = selectedExpeditionId = 0;
                    selectedExpeditionTier = null; expeditionClaim = null; DrawActiveSection(true);
                }).interactable = !IsBusy;
            }
            else
            {
                if (mount == null) FlowLabel(content, "ExpeditionMissingMount", "This mount is no longer in your collection. Refresh to check your mounts.", 16, ink);
                else
                {
                    if (selectedExpeditionId == 0 && mount.active_expedition != null) selectedExpeditionId = mount.active_expedition.id;
                    var trip = FindExpedition(selectedExpeditionId);
                    if (trip != null) DrawExpeditionDetails(content, trip);
                    else if (selectedExpeditionId != 0) FlowLabel(content, "ExpeditionLoadingTrip", "Refresh to load this expedition's saved status.", 16, ink);
                    else
                    {
                        FlowLabel(content, "ExpeditionPlanExplanation", "Choose a trip length. Your mount will be away until it returns. Longer trips can bring more finds; rewards are saved when you claim them.", 16, ink);
                        foreach (var tier in new[] { "short", "standard", "long" })
                        {
                            string choice = tier;
                            int hours = tier == "short" ? 2 : tier == "standard" ? 4 : 8;
                            FlowButton(content, "ExpeditionTier_" + tier, (selectedExpeditionTier == tier ? "Selected · " : "") + Humanize(tier) + " · " + hours + " hours", () =>
                            {
                                selectedExpeditionTier = choice; DrawActiveSection();
                            }).interactable = CanCare && api.CanStartExpedition(mount.id, tier);
                        }
                        if (selectedExpeditionTier != null)
                        {
                            string tier = selectedExpeditionTier;
                            int hours = tier == "short" ? 2 : tier == "standard" ? 4 : 8;
                            FlowButton(content, "ConfirmExpeditionStartButton", "Start " + hours + "-hour expedition", () =>
                                StartCoroutine(SaveExpedition(mount.id, tier, 0))).interactable = CanCare && api.CanStartExpedition(mount.id, tier);
                        }
                    }
                }
                FlowButton(content, "BackExpeditionsButton", "Back to expeditions", () => OpenExpeditions(0, 0)).interactable = !IsBusy;
            }
            SectionFooter(Section.Bestiary);
        }

        private void DrawExpeditionDetails(RectTransform content, ExpeditionDto trip)
        {
            FlowLabel(content, "ExpeditionStatus_" + trip.id, trip.status == "claimed" ? "Already claimed" : trip.CanClaim ? "Ready to claim" : Humanize(trip.status), 22, ink);
            FlowLabel(content, "ExpeditionTier", Humanize(trip.tier) + " expedition", 18, ink);
            FlowLabel(content, "ExpeditionReturnsAt", "Returns: " + ReturnTime(trip.returns_at), 16, ink);
            expeditionCountdownLabel = FlowLabel(content, "ExpeditionCountdown", ExpeditionCountdown(trip), 16, ink);
            if (trip.status == "active")
                FlowButton(content, "ConfirmExpeditionClaimButton", "Claim expedition loot", () =>
                    StartCoroutine(SaveExpedition(trip.mount_id, null, trip.id))).interactable = CanCare && api.CanClaimExpedition(trip.id);
            FlowLabel(content, "ExpeditionFindsHeading", trip.status == "active" ? "Planned finds" : "Finds recorded for this trip", 19, ink);
            FlowLabel(content, "ExpeditionPlannedCoins", trip.loot.coins + " planned expedition coins", 16, ink);
            foreach (var item in trip.loot.items)
                FlowLabel(content, "ExpeditionFind_" + item.item_id, item.name + " · " + item.quantity, 16, ink);
            if (expeditionClaim == null || expeditionClaim.expedition_id != trip.id) return;
            if (expeditionClaim.freshly_claimed)
            {
                FlowLabel(content, "ExpeditionSavedCoins", "Expedition coins saved: " + expeditionClaim.coins_awarded, 19, ink);
                int salvage = 0;
                foreach (var item in expeditionClaim.items) salvage += item.salvaged_to_coins;
                if (salvage > 0) FlowLabel(content, "ExpeditionSalvageCoins", "Duplicate finds converted to " + salvage + " additional coins", 16, ink);
            }
            else FlowLabel(content, "ExpeditionPreviouslyClaimed", "This trip was already claimed. No rewards were awarded again.", 16, ink);
            if (careInventory == null || !careDataReady) return;
            FlowLabel(content, "ExpeditionUpdatedInventory", "Your updated inventory", 19, ink);
            var shown = new HashSet<int>();
            foreach (var item in expeditionClaim.items)
            {
                if (!shown.Add(item.item_id)) continue;
                var entry = Array.Find(careInventory, value => value.item.id == item.item_id && value.quantity > 0);
                if (entry != null) FlowLabel(content, "ExpeditionSavedItem_" + item.item_id, entry.item.name + " · " + entry.quantity + " available", 16, ink);
            }
        }

        private static string ReturnTime(string value) => DateTimeOffset.TryParse(value, out var timestamp)
            ? timestamp.ToLocalTime().ToString("ddd, h:mm tt") : value;

        private string ExpeditionCountdown(ExpeditionDto trip)
        {
            if (trip.status != "active") return trip.status == "claimed" ? "Your mount has returned.\nThis trip's claim is saved." : "This trip is no longer active.";
            if (trip.is_ready) return "Ready to claim\nYour mount's return is confirmed.";
            int remaining = Mathf.Max(0, trip.seconds_remaining - Mathf.FloorToInt(Time.unscaledTime - expeditionsReadAt));
            if (remaining == 0) return "Time is up · Refresh to check.\nClaiming unlocks after the return is confirmed.";
            var duration = TimeSpan.FromSeconds(remaining);
            return "Estimated remaining: " + (duration.TotalHours >= 1 ? (int)duration.TotalHours + "h " : "") + duration.Minutes + "m " + duration.Seconds + "s\nRefresh to check the saved return status.";
        }

        private IEnumerator SaveExpedition(int mountId, string tier, int expeditionId)
        {
            if (!CanCare || !ExpeditionsOpen || (expeditionId > 0 ? !api.CanClaimExpedition(expeditionId) : !api.CanStartExpedition(mountId, tier))) yield break;
            var epoch = sessionEpoch;
            var view = viewVersion;
            var reviewKey = CareReviewKey;
            PlayerPrefs.SetInt(reviewKey, 1); PlayerPrefs.Save();
            careInFlight = true; careReviewLoaded = careDataReady = false; expeditionClaim = null;
            bestiaryStatus = expeditionId > 0 ? "Saving your expedition claim…" : "Starting your expedition…";
            DrawActiveSection(true);
            ApiError failure = null;
            ExpeditionDto started = null;
            ExpeditionClaimDto claimed = null;
            try
            {
                if (expeditionId > 0) yield return api.ClaimExpedition(expeditionId, value => claimed = value, error => failure = error);
                else yield return api.StartExpedition(mountId, tier, value => started = value, error => failure = error);
                if ((failure != null && !failure.OutcomeUnknown) || started != null || claimed != null)
                { PlayerPrefs.DeleteKey(reviewKey); PlayerPrefs.Save(); }
                if (!Current(epoch) || view != viewVersion) yield break;
                selectedExpeditionTier = null;
                if (failure == null && (started != null || claimed != null))
                {
                    if (started != null) selectedExpeditionId = started.id;
                    expeditionClaim = claimed;
                    string confirmed = started != null ? "Expedition started · Your mount is exploring." : claimed.freshly_claimed
                        ? "Expedition claimed · Your finds are saved." : "This expedition was already claimed.";
                    if (claimed != null && claimed.freshly_claimed) companion?.Celebrate();
                    Toast(confirmed, 7);
                    careInFlight = false;
                    yield return LoadSection(Section.Bestiary);
                    if (!Current(epoch) || view != viewVersion) yield break;
                    bestiaryStatus = confirmed + (careDataReady ? "" : " · Refresh to load your updated collection.");
                    nextHomeRefresh = 0;
                }
                else bestiaryStatus = failure != null && !failure.OutcomeUnknown
                    ? failure.Message + " Refresh your collection before trying again."
                    : "Couldn't confirm the expedition action. Refresh and check your expeditions, items and balance.";
            }
            finally
            {
                if (epoch == sessionEpoch && view == viewVersion)
                {
                    careInFlight = false;
                    if (IsDemo) ClearPresentation();
                    else { RefreshHud(); DrawActiveSection(true); }
                }
            }
        }

        private void DrawCareReview(RectTransform content)
        {
            if (!CareNeedsReview || careInFlight) return;
            FlowLabel(content, "CareReviewMessage", "The last creature action may have saved. Refresh and check your creatures, expeditions, items and balance before doing anything else. Play won't repeat it.", 16, ink);
            if (careReviewLoaded && careInventory != null)
            {
                FlowLabel(content, "CareReviewCoins", "Saved balance: " + coins.balance + " coins", 18, ink);
                FlowLabel(content, "CareReviewFoodHeading", "Your updated inventory", 18, ink);
                bool anyItems = false;
                foreach (var entry in careInventory)
                    if (entry.quantity > 0)
                    { anyItems = true; FlowLabel(content, "CareReviewFood_" + entry.item.id, entry.item.name + " · " + entry.quantity + " available", 16, ink); }
                if (!anyItems) FlowLabel(content, "CareReviewEmptyFood", "No items in your inventory", 16, ink);
                FlowLabel(content, "ReviewExpeditionsHeading", "Your updated expeditions", 18, ink);
                if (expeditions.Length == 0) FlowLabel(content, "ReviewExpeditionsEmpty", "No expeditions saved", 16, ink);
                foreach (var trip in expeditions)
                    FlowLabel(content, "ReviewExpedition_" + trip.id, trip.potion_name + " " + trip.species_name + " · " + Humanize(trip.status) + " · " + ReturnTime(trip.returns_at), 16, ink);
            }
            FlowButton(content, "RefreshCareButton", "Refresh pets and inventory", () => StartCoroutine(LoadSection(Section.Bestiary))).interactable = !sectionLoading && !IsBusy;
            FlowButton(content, "AcknowledgeCareButton", "I checked the updated collection", () =>
            {
                if (!careReviewLoaded || sectionLoading || IsBusy) return;
                PlayerPrefs.DeleteKey(CareReviewKey); PlayerPrefs.Save();
                bestiaryStatus = "Collection checked. Choose your next care action.";
                DrawActiveSection();
            }).interactable = careReviewLoaded && !sectionLoading && !IsBusy;
        }

        private OwnedPetDto SelectedPet()
        {
            if (stable?.pets != null) foreach (var pet in stable.pets) if (pet.id == selectedPetId) return pet;
            return null;
        }

        private InventoryEntryDto[] CareSupplies(params string[] types)
        {
            if (careInventory == null) return null;
            var result = new List<InventoryEntryDto>();
            foreach (var entry in careInventory)
                if (entry.quantity > 0 && Array.IndexOf(types, entry.item.item_type) >= 0) result.Add(entry);
            return result.ToArray();
        }

        private void DrawHatchery()
        {
            BeginModal("Hatch a companion", "Choose an egg and potion from your saved inventory.");
            var content = modalScroll.content;
            FlowLabel(content, "BestiaryStatus", bestiaryStatus, 14, ink);
            DrawCareReview(content);
            FlowLabel(content, "HatchExplanation", "Hatching uses 1 egg and 1 potion. Your new companion joins your collection; choose it as active afterwards.", 16, ink);
            if (careInventory == null) FlowLabel(content, "HatchLoadingItems", "Refresh to load your eggs and potions.", 16, ink);
            else
            {
                var eggs = CareSupplies("egg");
                var potions = CareSupplies("potion");
                DrawHatchIngredients(content, eggs, true);
                DrawHatchIngredients(content, potions, false);
                InventoryEntryDto egg = Array.Find(eggs, entry => entry.item.id == selectedEggItemId);
                InventoryEntryDto potion = Array.Find(potions, entry => entry.item.id == selectedPotionItemId);
                if (egg != null && potion != null)
                {
                    FlowLabel(content, "HatchSelectedPair", egg.item.name + " + " + potion.item.name, 18, ink);
                    FlowButton(content, "ConfirmHatchButton", "Hatch with 1 egg + 1 potion", () =>
                        StartCoroutine(SaveCare(0, 0, false, egg.item.id, potion.item.id))).interactable = CanCare;
                }
            }
            FlowButton(content, "BackHatcheryButton", "Back to pets", () =>
            {
                hatcheryOpen = false; selectedEggItemId = selectedPotionItemId = 0; DrawActiveSection(true);
            }).interactable = !IsBusy;
            SectionFooter(Section.Bestiary);
        }

        private void DrawHatchIngredients(RectTransform content, InventoryEntryDto[] entries, bool eggs)
        {
            FlowLabel(content, eggs ? "HatchEggsHeading" : "HatchPotionsHeading", eggs ? "Your eggs" : "Your potions", 19, ink);
            if (entries.Length == 0)
                FlowLabel(content, eggs ? "HatchEmptyEggs" : "HatchEmptyPotions", eggs ? "No eggs in your inventory yet." : "No hatching potions in your inventory yet.", 16, ink);
            foreach (var entry in entries)
            {
                int itemId = entry.item.id;
                var row = Row(content, (eggs ? "EggRow_" : "PotionRow_") + itemId);
                FlowLabel(row, "HatchIngredientName", entry.item.name + " · " + entry.quantity + " available", 18, ink);
                if (!string.IsNullOrWhiteSpace(entry.item.description)) FlowLabel(row, "HatchIngredientDescription", entry.item.description, 14, ink);
                bool selected = itemId == (eggs ? selectedEggItemId : selectedPotionItemId);
                FlowButton(row, (eggs ? "Egg_" : "Potion_") + itemId, selected ? "Selected" : eggs ? "Choose this egg" : "Choose this potion", () =>
                {
                    if (eggs) selectedEggItemId = itemId; else selectedPotionItemId = itemId;
                    DrawActiveSection();
                }).interactable = CanCare;
            }
        }

        private void DrawPetCare()
        {
            var pet = SelectedPet();
            BeginModal("Companion care", pet == null ? "Refresh your collection." : PetName(pet));
            var content = modalScroll.content;
            FlowLabel(content, "BestiaryStatus", bestiaryStatus, 14, ink);
            DrawCareReview(content);
            if (pet != null)
            {
                FlowLabel(content, "CareGrowth", pet.evolved_to_mount ? "Evolved into a mount · See your collection" : pet.growth_points + " / 100 growth", 22, ink);
                if (!pet.evolved_to_mount)
                {
                    FlowLabel(content, "CareExplanation", "Give one food from your inventory. Growth and evolution are saved to your account.", 16, ink);
                    if (!string.IsNullOrWhiteSpace(pet.species.food_preference))
                        FlowLabel(content, "FoodPreference", "Favorite food: " + pet.species.food_preference, 16, ink);
                    if (foodInventory == null) FlowLabel(content, "LoadingFood", "Refresh to load your food.", 16, ink);
                    else if (foodInventory.Length == 0) FlowLabel(content, "EmptyFood", "No food in your inventory yet. Food you earn will appear here.", 16, ink);
                    else foreach (var entry in foodInventory)
                    {
                        var itemId = entry.item.id;
                        var row = Row(content, "FoodRow_" + itemId);
                        FlowLabel(row, "FoodName", entry.item.name + " · " + entry.quantity + " available", 18, ink);
                        if (!string.IsNullOrWhiteSpace(entry.item.description)) FlowLabel(row, "FoodDescription", entry.item.description, 14, ink);
                        FlowButton(row, "Food_" + itemId, selectedFoodItemId == itemId ? "Selected" : "Choose this food", () =>
                        {
                            selectedFoodItemId = itemId; DrawActiveSection();
                        }).interactable = CanCare;
                        if (selectedFoodItemId == itemId)
                            FlowButton(row, "ConfirmFeedButton", "Give 1 " + entry.item.name, () => StartCoroutine(SaveCare(pet.id, itemId, false))).interactable = CanCare;
                    }
                }
            }
            FlowButton(content, "BackCareButton", "Back to pets", () => { selectedPetId = selectedFoodItemId = 0; DrawActiveSection(true); }).interactable = !IsBusy;
            SectionFooter(Section.Bestiary);
        }

        private IEnumerator SaveCare(int creatureId, int foodItemId, bool mount, int eggItemId = 0, int potionItemId = 0)
        {
            if (!CanCare || section != Section.Bestiary) yield break;
            var epoch = sessionEpoch;
            var view = viewVersion;
            var reviewKey = CareReviewKey;
            // Persist before dispatch: an abort or process exit cannot establish
            // whether Django committed. Only a definite result removes this marker.
            PlayerPrefs.SetInt(reviewKey, 1); PlayerPrefs.Save();
            careInFlight = true; careReviewLoaded = careDataReady = false;
            bool hatching = eggItemId > 0 || potionItemId > 0;
            bestiaryStatus = hatching ? "Hatching your companion…" : foodItemId > 0 ? "Saving this feeding…" : "Saving your choice…";
            DrawActiveSection(hatching);
            ApiError failure = null;
            PetFeedDto fed = null;
            OwnedPetDto activePet = null;
            OwnedMountDto activeMount = null;
            OwnedPetDto hatchedPet = null;
            try
            {
                if (hatching) yield return api.HatchPet(eggItemId, potionItemId, value => hatchedPet = value, error => failure = error);
                else if (foodItemId > 0) yield return api.FeedPet(creatureId, foodItemId, value => fed = value, error => failure = error);
                else if (mount) yield return api.ActivateMount(creatureId, value => activeMount = value, error => failure = error);
                else yield return api.ActivatePet(creatureId, value => activePet = value, error => failure = error);
                if ((failure != null && !failure.OutcomeUnknown) || fed != null || activePet != null || activeMount != null || hatchedPet != null)
                { PlayerPrefs.DeleteKey(reviewKey); PlayerPrefs.Save(); }
                if (!Current(epoch) || view != viewVersion) yield break;
                selectedFoodItemId = selectedEggItemId = selectedPotionItemId = 0;
                if (failure == null && (fed != null || activePet != null || activeMount != null || hatchedPet != null))
                {
                    if (activePet != null) RememberCompanion(OwnedCompanionChoice.FromPet(activePet));
                    else if (activeMount != null) RememberCompanion(OwnedCompanionChoice.FromMount(activeMount));
                    else if (fed != null && presentedCompanion.Kind == OwnedCompanionKind.Pet && presentedCompanion.CreatureId == creatureId)
                        RememberCompanion(presentedCompanion.WithConfirmedFeed(creatureId, fed));
                    string confirmed = hatchedPet != null ? "Hatch saved · " + hatchedPet.DisplayName + " joined your collection!" : fed != null ? fed.evolved
                        ? "Feeding saved · Your companion evolved into a mount!"
                        : "Feeding saved · " + fed.new_growth + " / 100 growth"
                        : "Your active " + (mount ? "mount" : "companion") + " is saved.";
                    companion?.Celebrate(); Toast(confirmed, 7);
                    careInFlight = false;
                    yield return LoadSection(Section.Bestiary);
                    if (!Current(epoch) || view != viewVersion) yield break;
                    bestiaryStatus = confirmed + (careDataReady ? "" : " · Refresh to load your updated collection.");
                    nextHomeRefresh = 0;
                }
                else
                    bestiaryStatus = failure != null && !failure.OutcomeUnknown
                        ? failure.Message + " Refresh your collection before trying again."
                        : "Couldn't confirm the care action. Refresh and check your collection.";
            }
            finally
            {
                if (epoch == sessionEpoch && view == viewVersion)
                {
                    careInFlight = false;
                    if (IsDemo) ClearPresentation();
                    else { RefreshHud(); DrawActiveSection(hatching); }
                }
            }
        }

        private void OpenConnection()
        {
            if (IsBusy) return;
            section = IsDemo ? Section.Connect : Section.Account;
            viewVersion++;
            sectionLoading = false;
            if (!IsDemo)
            {
                BeginModal("Your account", api.CurrentUser.DisplayName);
#if UNITY_WEBGL && !UNITY_EDITOR
                FlowLabel(modalScroll.content, "AccountExplanation", "Your journal and Play share this account and its saved progress.", 17, ink);
#else
                FlowLabel(modalScroll.content, "AccountExplanation", "Play shows this account's saved progress. Web shortcuts open your browser, which uses its own sign-in.", 17, ink);
#endif
                FlowButton(modalScroll.content, "RefreshHomeButton", "Refresh progress", () => { CloseModal(); StartCoroutine(RefreshHome()); });
                FlowButton(modalScroll.content, "DisconnectButton", "Disconnect Play", () => { api.ClearSession(); ClearPresentation(); Toast("Play is disconnected. Your web account is still signed in."); });
                FooterButton("CloseAccountButton", "Close", CloseModal);
            }
            else
            {
#if UNITY_WEBGL && !UNITY_EDITOR
                BeginModal("Connect your account", "The same account as your journal.");
                FlowLabel(modalScroll.content, "ConnectionMessage", "Sign in on the web app, then return to Play.", 17, ink);
                FlowButton(modalScroll.content, "OpenJournalButton", "Open Today and sign in", () => Navigate(PlayDestination.Today));
                FlowButton(modalScroll.content, "ResumeJournalButton", "Connect signed-in account", () => { CloseModal(); browserSessionDirty = true; });
                FooterButton("CancelConnectionButton", "Close", CloseModal);
#else
                BeginModal("Connect your account", "Your existing Abby account.");
                FlowLabel(modalScroll.content, "ServerAddressLabel", "Server address", 15, ink);
                var server = FlowInput(modalScroll.content, "ServerAddressInput", api.BaseUrl, "https://your-abby-app.example", false);
                server.keyboardType = TouchScreenKeyboardType.URL;
                FlowLabel(modalScroll.content, "UsernameLabel", "Username", 15, ink);
                var username = FlowInput(modalScroll.content, "UsernameInput", "", "Your child account", false);
                FlowLabel(modalScroll.content, "PasswordLabel", "Password", 15, ink);
                var password = FlowInput(modalScroll.content, "PasswordInput", "", "Password", true);
                var message = FlowLabel(modalScroll.content, "ConnectionMessage", "Your password is never saved in Play.", 15, ink);
                Button submit = null;
                Button cancel = null;
                submit = FooterButton("ConnectAccountButton", "Connect", () =>
                {
                    if (busy) return;
                    if (!api.ConfigureBaseUrl(server.text, out var error)) { message.text = error; return; }
                    if (string.IsNullOrWhiteSpace(username.text) || string.IsNullOrEmpty(password.text)) { message.text = "Enter your username and password."; return; }
                    StartCoroutine(Connect(username.text.Trim(), password.text, message, submit, cancel)); password.text = "";
                });
                cancel = FooterButton("CancelConnectionButton", "Close", CloseModal);
#endif
            }
            LayoutInterface();
        }

        private IEnumerator Connect(string username, string password, Text message, Button submit, Button cancel)
        {
            var epoch = sessionEpoch;
            busy = true; submit.interactable = cancel.interactable = false; message.text = "Connecting…";
            UserDto user = null; ApiError failure = null;
            yield return api.Login(username, password, value => user = value, error => failure = error);
            if (epoch != sessionEpoch) yield break;
            busy = false;
            if (failure != null || user == null || user.role != "child")
            {
                if (user != null && user.role != "child") api.ClearSession();
                message.text = failure == null ? "Play uses a child account. Parent tools are in the web app." : failure.Message;
                submit.interactable = cancel.interactable = true; RefreshHud(); yield break;
            }
            toastPanel.gameObject.SetActive(false);
            CloseModal(); RefreshHud(); yield return RefreshHome();
        }

        private static string PetName(OwnedPetDto pet) => string.IsNullOrWhiteSpace(pet.name) ? pet.species.name : pet.name;
        private static string Shorten(string value, int length) => string.IsNullOrEmpty(value) || value.Length <= length ? value : value.Substring(0, length - 1) + "…";
        private static string Humanize(string value) => string.IsNullOrWhiteSpace(value) ? "" : value.Replace('_', ' ');
        private static string Date(string value) => DateTimeOffset.TryParse(value, out var date) ? date.LocalDateTime.ToString("d MMM yyyy") : "";

        private RectTransform Row(RectTransform parent, string name)
        {
            var row = Panel(parent, name, Vector2.zero, Vector2.up, Vector2.up, Vector2.zero, new Color(teal.r, teal.g, teal.b, .08f));
            VerticalFlow(row, 12, 6);
            return row;
        }

        private void BeginModal(string title, string subtitle)
        {
            if (modal != null) { modal.SetActive(false); Destroy(modal); }
            var backdrop = Panel(canvas, "ModalBackdrop", Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero, new Color(ink.r, ink.g, ink.b, .7f));
            backdrop.anchorMax = Vector2.one; backdrop.offsetMin = backdrop.offsetMax = Vector2.zero;
            modal = backdrop.gameObject;
            modalSafeArea = Box(backdrop, "ModalSafeArea", Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            modalSheet = Panel(modalSafeArea, "CampSheet", Vector2.zero, new Vector2(.5f, .5f), new Vector2(.5f, .5f), Vector2.zero, paper);
            modalTitle = Label(modalSheet, title, 25, Vector2.zero, Vector2.zero, TextAnchor.UpperLeft, ink); modalTitle.name = "SheetTitle";
            modalTitle.verticalOverflow = VerticalWrapMode.Overflow;
            modalSubtitle = Label(modalSheet, subtitle, 15, Vector2.zero, Vector2.zero, TextAnchor.UpperLeft, ink); modalSubtitle.name = "SheetSubtitle";
            var viewport = Panel(modalSheet, "SheetViewport", Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero, new Color(0, 0, 0, .02f));
            viewport.anchorMax = Vector2.one;
            viewport.gameObject.AddComponent<RectMask2D>();
            var content = Box(viewport, "SheetContent", Vector2.zero, Vector2.up, Vector2.up, Vector2.zero);
            content.anchorMax = Vector2.one; content.anchorMin = Vector2.up;
            VerticalFlow(content, 0, 12);
            content.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            modalScroll = viewport.gameObject.AddComponent<ScrollRect>();
            modalScroll.horizontal = false; modalScroll.viewport = viewport; modalScroll.content = content;
            modalScroll.movementType = ScrollRect.MovementType.Clamped; modalScroll.scrollSensitivity = 24;
            modalFooter = Box(modalSheet, "SheetActions", Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            var layout = modalFooter.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.spacing = 12; layout.childControlHeight = layout.childControlWidth = layout.childForceExpandWidth = true; layout.childForceExpandHeight = false;
            gardenInput?.SetInputEnabled(false);
        }

        private void CloseModal() { if (!IsBusy) DismissModal(); }

        private void DismissModal()
        {
            if (modal != null) { modal.SetActive(false); Destroy(modal); }
            modal = null; modalSheet = null; modalSafeArea = null; modalScroll = null; modalFooter = null;
            section = Section.None; viewVersion++; sectionLoading = false;
            gardenInput?.SetInputEnabled(true);
        }

        private void LayoutInterface()
        {
            if (safeArea == null || headingPanel == null) return;
            revealFocusedInput = true;
            var size = safeArea.rect.size;
            var landscape = phoneLayout.IsLandscape;
            var width = Mathf.Max(1, size.x - 24);
            var headerWidth = landscape ? Mathf.Min(width, 430) : width;
            Place(headingPanel, new Vector2(12, -12), new Vector2(headerWidth, 112));
            Place(titleLabel.rectTransform, new Vector2(12, -8), new Vector2(headerWidth - 218, 38));
            Place(connectButton.GetComponent<RectTransform>(), new Vector2(headerWidth - 196, -10), new Vector2(104, 44));
            Place(todayButton.GetComponent<RectTransform>(), new Vector2(headerWidth - 84, -10), new Vector2(72, 44));
            ResizeButtonLabel(connectButton); ResizeButtonLabel(todayButton);
            Place(modeLabel.rectTransform, new Vector2(12, -50), new Vector2(headerWidth - 24, 20));
            Place(coinsLabel.rectTransform, new Vector2(12, -73), new Vector2(headerWidth - 24, 23));
            Place(homeStatusLabel.rectTransform, new Vector2(12, -95), new Vector2(headerWidth - 24, 16));
            var actionWidth = landscape ? Mathf.Min(350, width * .45f) : width;
            controlsPanel.anchorMin = controlsPanel.anchorMax = Vector2.zero; controlsPanel.pivot = Vector2.zero;
            controlsPanel.anchoredPosition = new Vector2(landscape ? size.x - actionWidth - 12 : 12, 12);
            controlsPanel.sizeDelta = new Vector2(actionWidth, 156);
            var buttonWidth = (actionWidth - 40) / 3;
            var cards = new[] { rewardsButton, inboxButton, bestiaryButton };
            for (int i = 0; i < cards.Length; i++)
            {
                Place(cards[i].GetComponent<RectTransform>(), new Vector2(12 + i * (buttonWidth + 8), -12), new Vector2(buttonWidth, 76));
                var labels = cards[i].GetComponentsInChildren<Text>();
                Place(labels[0].rectTransform, new Vector2(4, -10), new Vector2(buttonWidth - 8, 28));
                Place(labels[1].rectTransform, new Vector2(4, -40), new Vector2(buttonWidth - 8, 34));
                labels[0].fontSize = actionWidth < 335 ? 16 : 18;
            }
            var shortcuts = new[] { journalButton, gradesButton, tasksButton };
            for (int i = 0; i < shortcuts.Length; i++)
            {
                Place(shortcuts[i].GetComponent<RectTransform>(), new Vector2(12 + i * (buttonWidth + 8), -96), new Vector2(buttonWidth, 48));
                ResizeButtonLabel(shortcuts[i]);
            }
            var greetingWidth = landscape ? Mathf.Min(360, size.x - actionWidth - 36) : width;
            footerPanel.anchorMin = footerPanel.anchorMax = Vector2.zero; footerPanel.pivot = Vector2.zero;
            footerPanel.anchoredPosition = new Vector2(12, landscape ? 12 : 180); footerPanel.sizeDelta = new Vector2(greetingWidth, 68);
            Place(companionNameLabel.rectTransform, new Vector2(12, -8), new Vector2(greetingWidth - 136, 27));
            Place(companionHintLabel.rectTransform, new Vector2(12, -38), new Vector2(greetingWidth - 136, 24));
            Place(patButton.GetComponent<RectTransform>(), new Vector2(greetingWidth - 120, -10), new Vector2(108, 48)); ResizeButtonLabel(patButton);
            toastPanel.anchorMin = toastPanel.anchorMax = Vector2.zero; toastPanel.pivot = Vector2.zero;
            var toastWidth = landscape ? greetingWidth : width;
            toastPanel.anchoredPosition = new Vector2(12, landscape ? 88 : 260); toastPanel.sizeDelta = new Vector2(toastWidth, 52);
            Place(toastLabel.rectTransform, new Vector2(10, -4), new Vector2(toastWidth - 20, 44));
            if (modalSheet == null || modalSafeArea == null) return;
            modalSafeArea.anchorMin = safeArea.anchorMin; modalSafeArea.anchorMax = safeArea.anchorMax; modalSafeArea.offsetMin = modalSafeArea.offsetMax = Vector2.zero;
            var compact = size.y < 300;
            var sheetSize = new Vector2(Mathf.Min(580, size.x - 24), Mathf.Min(760, size.y - (compact ? 0 : 24)));
            modalSheet.sizeDelta = sheetSize;
            modalTitle.fontSize = compact ? 20 : 25;
            Place(modalTitle.rectTransform, new Vector2(16, compact ? -8 : -16), new Vector2(sheetSize.x - 32, 32));
            modalSubtitle.gameObject.SetActive(!compact);
            Place(modalSubtitle.rectTransform, new Vector2(16, -54), new Vector2(sheetSize.x - 32, 36));
            modalScroll.viewport.offsetMin = new Vector2(16, compact ? 64 : 76); modalScroll.viewport.offsetMax = new Vector2(-16, compact ? -44 : -94);
            modalFooter.anchorMin = modalFooter.anchorMax = Vector2.zero; modalFooter.pivot = Vector2.zero;
            modalFooter.anchoredPosition = new Vector2(16, compact ? 8 : 16); modalFooter.sizeDelta = new Vector2(sheetSize.x - 32, 48);
            Canvas.ForceUpdateCanvases();
            LayoutRebuilder.ForceRebuildLayoutImmediate(modalScroll.content);
            foreach (var button in modalSheet.GetComponentsInChildren<Button>()) ResizeButtonLabel(button);
        }

        private void KeepFocusedInputVisible()
        {
            if (modalScroll == null || EventSystem.current == null) return;
            var selected = EventSystem.current.currentSelectedGameObject;
            if (selected == null || selected.GetComponent<InputField>() == null || !selected.transform.IsChildOf(modalScroll.content))
            {
                lastFocusedInput = null;
                return;
            }
            if (selected == lastFocusedInput && !revealFocusedInput) return;
            lastFocusedInput = selected;
            revealFocusedInput = false;
            // Reveal once on focus/resize, leaving the user free to scroll afterwards.
            LayoutRebuilder.ForceRebuildLayoutImmediate(modalScroll.content);
            var bounds = RectTransformUtility.CalculateRelativeRectTransformBounds(modalScroll.viewport, selected.transform);
            var view = modalScroll.viewport.rect;
            var position = modalScroll.content.anchoredPosition;
            if (bounds.min.y < view.yMin + 12) position.y += view.yMin + 12 - bounds.min.y;
            else if (bounds.max.y > view.yMax - 12) position.y -= bounds.max.y - (view.yMax - 12);
            position.y = Mathf.Clamp(position.y, 0, Mathf.Max(0, modalScroll.content.rect.height - view.height));
            modalScroll.content.anchoredPosition = position;
        }

        /// <summary>Read-only sizing diagnostics for device/viewport checks.</summary>
        public string DescribePhoneLayout()
        {
            if (safeArea == null) return "Play UI has not started.";
            return $"Play UI: screen={Screen.width}x{Screen.height}, safe={phoneLayout.UsableScreenRect}, logical={safeArea.rect.size}, minTarget=48, modal={(modalSheet == null ? Vector2.zero : modalSheet.rect.size)}";
        }

        public void LogPhoneLayout() => Debug.Log(DescribePhoneLayout());

        private static void Place(RectTransform rect, Vector2 position, Vector2 size)
        {
            rect.anchorMin = rect.anchorMax = new Vector2(0, 1);
            rect.pivot = new Vector2(0, 1);
            rect.anchoredPosition = position;
            rect.sizeDelta = size;
        }

        private static void ResizeButtonLabel(Button button)
        {
            var label = button.GetComponentInChildren<Text>();
            if (label == null) return;
            label.rectTransform.anchorMin = Vector2.zero;
            label.rectTransform.anchorMax = Vector2.one;
            label.rectTransform.offsetMin = new Vector2(8, 0);
            label.rectTransform.offsetMax = new Vector2(-8, 0);
        }

        private static void VerticalFlow(RectTransform rect, int padding, int spacing)
        {
            var layout = rect.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(padding, padding, padding, padding);
            layout.spacing = spacing;
            layout.childControlWidth = true;
            layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
        }

        private Text FlowLabel(RectTransform parent, string name, string value, int size, Color color, FontStyle style = FontStyle.Normal)
        {
            var text = Label(parent, value, size, Vector2.zero, Vector2.zero, TextAnchor.UpperLeft, color, style);
            text.name = name;
            text.supportRichText = false;
            // Flow layout already sizes these paragraphs from preferredHeight.
            // Fractional pixel rounding must not truncate a complete text line.
            text.verticalOverflow = VerticalWrapMode.Overflow;
            return text;
        }

        private Button FlowButton(RectTransform parent, string name, string label, Action clicked)
        {
            var button = Button(parent, label, Vector2.zero, new Vector2(100, 48), clicked);
            button.name = name;
            var layout = button.gameObject.AddComponent<LayoutElement>();
            layout.minHeight = layout.preferredHeight = 48;
            layout.flexibleWidth = 1;
            return button;
        }

        private Button FooterButton(string name, string label, Action clicked) => FlowButton(modalFooter, name, label, clicked);

        private InputField FlowInput(RectTransform parent, string name, string value, string placeholder, bool secret)
        {
            var input = InputField(parent, value, placeholder, Vector2.zero, secret);
            input.name = name;
            var layout = input.gameObject.AddComponent<LayoutElement>();
            layout.minHeight = layout.preferredHeight = 48;
            foreach (var text in input.GetComponentsInChildren<Text>())
            {
                text.rectTransform.anchorMin = Vector2.zero;
                text.rectTransform.anchorMax = Vector2.one;
                text.rectTransform.offsetMin = new Vector2(12, 6);
                text.rectTransform.offsetMax = new Vector2(-12, -6);
            }
            input.shouldHideMobileInput = false;
            return input;
        }

        private void Toast(string message, float duration = 5f)
        {
            if (toastLabel == null) return;
            toastLabel.text = message;
            toastPanel.gameObject.SetActive(true);
            toastUntil = Time.unscaledTime + duration;
        }

        private RectTransform Box(Transform parent, string name, Vector2 size, Vector2 anchor, Vector2 pivot, Vector2 position)
        {
            var go = new GameObject(name, typeof(RectTransform));
            var rect = go.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.anchorMin = anchor;
            rect.anchorMax = anchor;
            rect.pivot = pivot;
            rect.sizeDelta = size;
            rect.anchoredPosition = position;
            return rect;
        }

        private RectTransform Panel(Transform parent, string name, Vector2 size, Vector2 anchor, Vector2 pivot, Vector2 position, Color color)
        {
            var rect = Box(parent, name, size, anchor, pivot, position);
            var image = rect.gameObject.AddComponent<Image>();
            image.color = color;
            if (name != "ModalBackdrop")
            {
                image.sprite = CampUiShapes.RoundedPanel;
                image.type = Image.Type.Sliced;
            }
            return rect;
        }

        private Text Label(Transform parent, string value, int size, Vector2 position, Vector2 dimensions, TextAnchor alignment, Color color, FontStyle style = FontStyle.Normal)
        {
            var rect = Box(parent, "Label", dimensions, new Vector2(0, 1), new Vector2(0, 1), position);
            var text = rect.gameObject.AddComponent<Text>();
            text.font = font;
            text.text = value;
            text.supportRichText = false;
            text.fontSize = size;
            // The shared file is already the 600-weight static face. Asking
            // Unity for Bold can synthesize thickness or select another face.
            text.fontStyle = presentation != null && font == presentation.UiFont ? FontStyle.Normal : style;
            text.color = color;
            text.alignment = alignment;
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
            text.verticalOverflow = VerticalWrapMode.Truncate;
            text.raycastTarget = false;
            return text;
        }

        private Button Button(Transform parent, string label, Vector2 position, Vector2 size, Action clicked, bool quiet = false)
        {
            var rect = Panel(parent, label, size, new Vector2(0, 1), new Vector2(0, 1), position, quiet ? new Color(teal.r, teal.g, teal.b, .12f) : teal);
            var button = rect.gameObject.AddComponent<Button>();
            button.targetGraphic = rect.GetComponent<Image>();
            var colors = button.colors;
            colors.highlightedColor = new Color(1.10f, 1.10f, 1.10f);
            colors.pressedColor = new Color(0.75f, 0.85f, 0.80f);
            colors.disabledColor = new Color(0.55f, 0.55f, 0.55f, 0.65f);
            button.colors = colors;
            button.onClick.AddListener(() => clicked());
            Label(rect, label, quiet ? 14 : 16, Vector2.zero, size, TextAnchor.MiddleCenter, quiet ? teal : Color.white, FontStyle.Bold);
            return button;
        }

        private InputField InputField(Transform parent, string value, string placeholder, Vector2 position, bool secret)
        {
            var rect = Panel(parent, "Input", new Vector2(564, 48), new Vector2(0, 1), new Vector2(0, 1), position, Color.white);
            var input = rect.gameObject.AddComponent<InputField>();
            var text = Label(rect, "", 18, new Vector2(12, -7), new Vector2(540, 34), TextAnchor.MiddleLeft, ink);
            text.supportRichText = false;
            var hint = Label(rect, placeholder, 18, new Vector2(12, -7), new Vector2(540, 34), TextAnchor.MiddleLeft, new Color(0.45f, 0.49f, 0.49f));
            hint.supportRichText = false;
            input.textComponent = text;
            input.placeholder = hint;
            input.contentType = secret ? UnityEngine.UI.InputField.ContentType.Password : UnityEngine.UI.InputField.ContentType.Standard;
            input.characterLimit = secret ? 256 : 2048;
            input.text = value;
            return input;
        }
    }
}
