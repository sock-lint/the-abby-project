#if UNITY_EDITOR || DEVELOPMENT_BUILD
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using AbbyCamp.Data;
using AbbyCamp.Services;
using AbbyCamp.UI;
using AbbyCamp.World;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;

namespace AbbyCamp.Validation
{
    /// <summary>Opt-in Play smoke against disposable loopback APIs. Views and
    /// greetings must not award anything; inbox and care mutations require confirmation.</summary>
    public sealed class CampRuntimeSmoke : MonoBehaviour
    {
        private static readonly string[] HomeButtons = {
            "RewardsButton", "InboxButton", "BestiaryButton", "JournalButton",
            "GradesButton", "TasksButton", "PatCompanionButton", "AccountButton", "TodayButton"
        };
        private readonly List<string> checks = new List<string>();
        private readonly List<string> runtimeErrors = new List<string>();
        private bool failed, failFirstMarkRead, ambiguousFeed, ambiguousHatch, ambiguousExpeditionStart, ambiguousExpeditionClaim, ownedCreatureArt;
        private string output, fixtureUrl, username, password, secondUsername, secondPassword;

        [Serializable] private sealed class FixtureState { public FixtureAccount[] accounts; }
        [Serializable] private sealed class FixtureAccount
        {
            public int user_id, balance, inventory_quantity, skill_xp, notification_count;
            public int feed_requests, feed_commits, hatch_requests, hatch_commits, care_responses_pending, care_hold_timeouts;
            public int expedition_start_requests, expedition_start_commits, expedition_claim_requests, expedition_claim_commits;
            public int[] ledger_ids, drop_ids, unread_ids;
            public FixtureLedger[] ledger;
            public FixturePet[] pets;
            public FixtureMount[] mounts;
            public FixtureFood[] food;
            public FixtureItem[] items;
            public FixtureExpedition[] expeditions;
        }
        [Serializable] private sealed class FixturePet { public int id, growth_points, species_id, potion_id; public bool is_active, evolved_to_mount; }
        [Serializable] private sealed class FixtureMount { public int id; public bool is_active; public string potion_name; }
        [Serializable] private sealed class FixtureFood { public int item_id, quantity; }
        [Serializable] private sealed class FixtureItem { public int item_id, quantity; public string item_type, name; }
        [Serializable] private sealed class FixtureLedger { public int id, amount; public string reason; }
        [Serializable] private sealed class FixtureExpedition
        {
            public int id, mount_id; public bool is_ready;
            public string tier, status, started_at, returns_at, claimed_at;
            public FixtureLoot loot;
        }
        [Serializable] private sealed class FixtureLoot { public int coins; public FixtureLootItem[] items; }
        [Serializable] private sealed class FixtureLootItem { public int item_id, quantity; public string name, rarity, item_type, icon, sprite_key; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void Bootstrap()
        {
            var args = Environment.GetCommandLineArgs();
            if (Array.IndexOf(args, "--abby-smoke") < 0) return;
            var instance = new GameObject("DevelopmentSmoke").AddComponent<CampRuntimeSmoke>();
            DontDestroyOnLoad(instance.gameObject);
            instance.output = Argument(args, "--abby-smoke-output") ?? Path.Combine(Application.persistentDataPath, "Smoke");
            instance.fixtureUrl = Argument(args, "--abby-api-url");
            instance.username = Argument(args, "--abby-api-user");
            instance.password = Argument(args, "--abby-api-password");
            instance.secondUsername = Argument(args, "--abby-api-second-user");
            instance.secondPassword = Argument(args, "--abby-api-second-password");
            instance.failFirstMarkRead = Array.IndexOf(args, "--abby-smoke-failed-mark-read") >= 0;
            instance.ambiguousFeed = Array.IndexOf(args, "--abby-smoke-ambiguous-feed") >= 0;
            instance.ambiguousHatch = Array.IndexOf(args, "--abby-smoke-ambiguous-hatch") >= 0;
            instance.ambiguousExpeditionStart = Array.IndexOf(args, "--abby-smoke-ambiguous-expedition-start") >= 0;
            instance.ambiguousExpeditionClaim = Array.IndexOf(args, "--abby-smoke-ambiguous-expedition-claim") >= 0;
            instance.ownedCreatureArt = Array.IndexOf(args, "--abby-smoke-owned-creature-art") >= 0;
            Directory.CreateDirectory(instance.output);
            Application.runInBackground = true;
        }

        private static string Argument(string[] args, string name)
        {
            int index = Array.IndexOf(args, name);
            return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
        }

        private void Start()
        {
            Application.logMessageReceived += ObserveLog;
            StartCoroutine(Monitor(Run()));
        }

        private void ObserveLog(string message, string trace, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert) runtimeErrors.Add(message);
        }

        private IEnumerator Monitor(IEnumerator routine)
        {
            while (!failed)
            {
                object step = null;
                bool moved = false;
                Exception problem = null;
                try { moved = routine.MoveNext(); if (moved) step = routine.Current; }
                catch (Exception exception) { problem = exception; }
                if (problem != null) { Finish(false, problem.ToString()); yield break; }
                if (!moved) yield break;
                if (step is IEnumerator nested && !(step is CustomYieldInstruction)) yield return Monitor(nested);
                else yield return step;
            }
        }

        private IEnumerator Run()
        {
            for (int frame = 0; frame < 25; frame++) yield return null;
            var ui = FindFirstObjectByType<CampPrototypeController>();
            var garden = FindFirstObjectByType<CampGardenInput>();
            var pet = FindFirstObjectByType<CompanionFollower>();
            var camera = Camera.main;
            Check(ui != null && garden != null && pet != null && camera != null, "Play home, companion, garden input and camera are present");
            Check(FindFirstObjectByType<CampPlayerController>() == null && FindFirstObjectByType<CampTaskBoard>() == null,
                "Play contains no walking avatar or task board");
            Check(pet.GetComponent<CharacterController>() == null, "The stationary companion has no movement controller");
            Check(ui.IsDemo && !ui.IsModalOpen && garden.InputEnabled, "Play boots into a usable preview home");
            yield return Resize(393, 852);
            CheckHomeTargets();
            yield return Capture("play-home-portrait.png");
            yield return CheckDensityInvariant(ui, garden, pet, camera, 393, 852, "portrait");
            yield return CheckKeyboardTargets(ui, garden);
            var cameraPosition = camera.transform.position;
            var cameraRotation = camera.transform.rotation;
            var petPosition = pet.transform.position;
            var touchPoint = CompanionPoint(pet, camera);
            var groundPoint = (Vector2)camera.WorldToScreenPoint(petPosition + Vector3.right * 3f);
            Check(!garden.TryTapCompanion(groundPoint), "A ground tap cannot move an avatar or greet the companion");
            Check(garden.TryTapCompanion(touchPoint), "A touch inside visible companion bounds invokes its greeting");
            for (int frame = 0; frame < 15; frame++) yield return null;
            CheckStableWorld(camera, pet, cameraPosition, cameraRotation, petPosition);
            var identity = pet.GetComponent<CampEntityIdentity>();
            Check(identity != null && !string.IsNullOrEmpty(identity.ContentId), "Companion has a stable presentation identity");
            var rootId = pet.gameObject.GetEntityId();
            var contentId = identity.ContentId;
            var originalVisual = pet.Appearance.Definition;
            pet.ToggleAppearance();
            yield return null;
            Check(pet.gameObject.GetEntityId() == rootId && identity.ContentId == contentId && pet.Appearance.Definition != originalVisual,
                "Replaceable companion art preserves its home root and identity");
            pet.ToggleAppearance();
            foreach (string section in new[] { "Rewards", "Inbox", "Bestiary" })
            {
                yield return OpenSection(ui, garden, section);
                Check(!garden.TryTapCompanion(touchPoint), section + " modal blocks companion touches");
                Check(!HasNamedPrefix("Pet_") && !HasNamedPrefix("Mount_"), "Preview " + section + " does not invent owned creatures");
                yield return Capture("preview-" + section.ToLowerInvariant() + "-portrait.png");
                yield return CloseSection(ui, garden, section);
            }

            if (!string.IsNullOrEmpty(fixtureUrl))
            {
                Check(Uri.TryCreate(fixtureUrl, UriKind.Absolute, out var origin) && origin.IsLoopback
                    && origin.Scheme == Uri.UriSchemeHttp && origin.AbsolutePath == "/" && string.IsNullOrEmpty(origin.UserInfo)
                    && string.IsNullOrEmpty(origin.Query) && string.IsNullOrEmpty(origin.Fragment),
                    "Runtime smoke accepts only a disposable loopback HTTP origin");
                Check(!string.IsNullOrEmpty(secondUsername) && !string.IsNullOrEmpty(secondPassword), "Fixture supplies a second account");
                FixtureState before = null, after = null;
                yield return ReadFixtureState(value => before = value);
                yield return Connect(ui, garden, username, password);
                var api = ui.GetComponent<AbbyApiClient>();
                Check(api.IsAuthenticated && api.CurrentUser.role == "child" && !ui.IsDemo, "Django child login succeeds through the Play account form");
                int primaryUser = api.CurrentUser.id;
                var initial = Account(before, primaryUser);
                ApiError problem = null;
                CoinBalanceDto coins = null;
                DropDto[] drops = null;
                StableDto stable = null;
                NotificationPageDto notices = null;
                yield return api.FetchCoins(value => coins = value, error => problem = error);
                yield return api.FetchRecentDrops(value => drops = value, error => problem = error);
                yield return api.FetchStable(value => stable = value, error => problem = error);
                Check(problem == null && coins != null && coins.balance == initial.balance && drops != null && drops.Length == initial.drop_ids.Length,
                    "Connected home reads persisted coins and drop history");
                Check(stable != null && stable.pets.Length == 2 && stable.mounts.Length == initial.mounts.Length && stable.pets[0].name == "Peep",
                    "The server returns the child's real companions and mounts");
                int stableReplies = 0, foodReplies = 0;
                ApiError simultaneousReadError = null;
                for (int read = 0; read < 2; read++)
                {
                    StartCoroutine(api.FetchStable(value => stableReplies++, error => simultaneousReadError = error));
                    StartCoroutine(api.FetchFoodInventory(value => foodReplies++, error => simultaneousReadError = error));
                }
                yield return WaitUntil(() => simultaneousReadError != null || stableReplies == 2 && foodReplies == 2, 15f,
                    "Concurrent stable and food reads finish");
                Check(simultaneousReadError == null && stableReplies == 2 && foodReplies == 2,
                    "Overlapping collection refreshes safely replace known owned IDs without duplicate-cache errors");
                int primaryPet = stable.pets[0].id, primaryMount = stable.mounts[0].id;
                if (ownedCreatureArt)
                {
                    CheckOwnedModel(ui, "cute-chick", AbbyCamp.Presentation.OwnedCompanionKind.Pet, stable.ActiveCompanion.id);
                    var appearanceId = pet.transform.Find("Appearance").gameObject.GetEntityId();
                    pet.ToggleAppearance();
                    for (int frame = 0; frame < 5; frame++) yield return null;
                    Check(pet.transform.Find("Appearance").gameObject.GetEntityId() == appearanceId
                        && NamedText("CompanionName") == "Peep", "Owned model refresh and development swap preserve the selected appearance instance");
                    yield return Capture("owned-chick-home-portrait.png");
                }
                else Check(NamedText("CompanionName") == "Meadow friend" && HasText("Artwork preview") && NamedText("CoinsBalance").Contains(initial.balance.ToString()),
                    "Home reports saved coins while honestly labeling the artwork preview");
                yield return OpenSection(ui, garden, "Rewards");
                yield return Capture("connected-rewards-portrait.png");
                yield return CloseSection(ui, garden, "Rewards");
                yield return OpenSection(ui, garden, "Bestiary");
                Check(HasNamed("Pet_" + primaryPet) && HasNamed("Mount_" + primaryMount) && NamedText("PetName_" + primaryPet).Contains("Peep")
                    && NamedText("ActiveCompanion").Contains("Peep"),
                    "Bestiary renders actual owned IDs and the saved pet name");
                yield return Capture("connected-bestiary-portrait.png");
                yield return CloseSection(ui, garden, "Bestiary");
                Click("PatCompanionButton");
                Check(garden.TryTapCompanion(CompanionPoint(pet, camera)), "Signed-in companion still supports bounded touch");
                for (int frame = 0; frame < 15; frame++) yield return null;
                CheckStableWorld(camera, pet, cameraPosition, cameraRotation, petPosition);
                yield return OpenSection(ui, garden, "Inbox");
                yield return api.FetchNotifications(value => notices = value, error => problem = error);
                Check(problem == null && notices != null && notices.count == initial.notification_count && notices.count > 20
                    && notices.results.Length == 20 && NamedRowCount("Notification_") == 20 && !string.IsNullOrEmpty(notices.next),
                    "Inbox renders a production-sized twenty-row first page from saved history");
                yield return ReadFixtureState(value => after = value);
                CheckAwardsUnchanged(before, after, "Home, greetings and all view sections award or consume nothing");
                Check(EqualIds(initial.unread_ids, Account(after, primaryUser).unread_ids), "Opening the inbox does not mark anything read");
                var notification = Array.Find(notices.results, row => !row.is_read);
                Check(notification != null && HasNamed("Notification_" + notification.id) && FindButton("MarkRead_" + notification.id) != null,
                    "An unread server row exposes an explicit read action");
                Click("MarkRead_" + notification.id);
                yield return WaitUntil(() => !ui.IsBusy, 15f, "First mark-read request finishes");
                if (failFirstMarkRead)
                {
                    yield return ReadFixtureState(value => after = value);
                    Check(EqualIds(initial.unread_ids, Account(after, primaryUser).unread_ids), "A rejected mark-read leaves server unread state unchanged");
                    Check(FindButton("MarkRead_" + notification.id)?.interactable == true, "A failed mark-read remains explicitly retryable");
                    Click("MarkRead_" + notification.id);
                    yield return WaitUntil(() => !ui.IsBusy, 15f, "Retried mark-read request finishes");
                }
                yield return ReadFixtureState(value => after = value);
                var readState = Account(after, primaryUser);
                Check(readState.unread_ids.Length == initial.unread_ids.Length - 1 && Array.IndexOf(readState.unread_ids, notification.id) < 0,
                    "Confirmed mark-read changes exactly the selected notification");
                foreach (int id in initial.unread_ids)
                    if (id != notification.id) Check(Array.IndexOf(readState.unread_ids, id) >= 0, "Other notification stays unread: " + id);
                CheckAwardsUnchanged(before, after, "Reading a notification changes no rewards or skill XP");
                string unreadLabel = NamedText("UnreadCount"), firstRows = NamedRows("Notification_");
                Click("NextInboxPageButton");
                yield return WaitUntil(() => !ui.IsSectionLoading && !ui.IsBusy, 15f, "Next inbox page finishes");
                Check(NamedRows("Notification_") != firstRows && NamedRowCount("Notification_") == initial.notification_count - 20
                    && NamedText("UnreadCount") == unreadLabel, "Next page changes displayed IDs without clearing global unread count");
                yield return Capture("connected-inbox-next-page-portrait.png");
                Click("PreviousInboxPageButton");
                yield return WaitUntil(() => !ui.IsSectionLoading && !ui.IsBusy, 15f, "Previous inbox page finishes");
                Check(NamedRows("Notification_") == firstRows && NamedText("UnreadCount") == unreadLabel, "Previous page restores its rows and preserves unread count");
                yield return CloseSection(ui, garden, "Inbox");
                yield return ExerciseCare(ui, garden, api, primaryUser, primaryPet, primaryMount, value => before = value);
                yield return ExerciseHatching(ui, garden, api, primaryUser, value => before = value);
                yield return ExerciseExpeditions(ui, garden, api, primaryUser, primaryMount, value => before = value);
                if (ownedCreatureArt)
                {
                    yield return OpenSection(ui, garden, "Bestiary");
                    yield return api.FetchStable(value => stable = value, error => problem = error);
                    var evolvedPet = Array.Find(stable.pets, row => row.id == primaryPet);
                    var grownMount = Array.Find(stable.mounts, row => row.species.id == evolvedPet.species.id && row.potion.id == evolvedPet.potion.id);
                    Click("ActiveMount_" + grownMount.id);
                    yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Owned Bird mount selection is acknowledged");
                    CheckOwnedModel(ui, "cute-bird", AbbyCamp.Presentation.OwnedCompanionKind.Mount, grownMount.id);
                    yield return CloseSection(ui, garden, "Bestiary");
                    yield return Capture("owned-bird-mount-home-portrait.png");
                }
                Click("AccountButton");
                yield return null;
                Click("DisconnectButton");
                yield return WaitUntil(() => ui.IsDemo && !ui.IsModalOpen && !ui.IsHomeLoading, 10f, "Disconnect clears the private home");
                Check(!api.IsAuthenticated && !HasText("Active: Peep") && !HasNamedPrefix("Notification_")
                    && !HasNamedPrefix("Pet_") && !HasNamedPrefix("Mount_"), "Disconnect clears old private labels and rows");
                Check(!ui.HasOwnedCompanionAppearance && ui.DisplayedCreatureId == 0, "Disconnect clears owned scene artwork and creature binding");
                problem = null;
                yield return api.FetchCoins(value => coins = value, error => problem = error);
                Check(problem != null && problem.RequiresLogin, "Disconnected reads require a validated session");
                yield return Connect(ui, garden, secondUsername, secondPassword);
                Check(api.IsAuthenticated && api.CurrentUser.id != primaryUser, "A second family's child can replace the session");
                problem = null;
                yield return api.FetchStable(value => stable = value, error => problem = error);
                yield return api.FetchCoins(value => coins = value, error => problem = error);
                var second = Account(before, api.CurrentUser.id);
                Check(problem == null && coins.balance == second.balance && stable.pets.Length == 1 && stable.pets[0].name == "Sprout",
                    "Replacement session reads only its own balance and stable");
                Check(NamedText("CompanionName") == "Meadow friend" && HasText("Artwork preview") && !HasText("Peep"),
                    "Replacement home keeps preview labeling and clears the previous saved companion");
                Check(!ui.HasOwnedCompanionAppearance, "Another family's unsupported creature cannot inherit the previous Bird model binding");
                yield return OpenSection(ui, garden, "Bestiary");
                Check(HasNamed("Pet_" + stable.pets[0].id) && NamedText("ActiveCompanion").Contains("Sprout")
                    && !HasNamed("Pet_" + primaryPet) && !HasNamed("Mount_" + primaryMount),
                    "Replacement Bestiary contains no previous-account owned IDs");
                yield return CloseSection(ui, garden, "Bestiary");
                yield return OpenSection(ui, garden, "Inbox");
                foreach (int id in initial.unread_ids) Check(!HasNamed("Notification_" + id), "Previous account notification is absent: " + id);
                Check(HasNamed("Notification_" + second.unread_ids[0]), "Inbox now belongs to the replacement account");
                yield return CloseSection(ui, garden, "Inbox");
                yield return ReadFixtureState(value => after = value);
                CheckAwardsUnchanged(before, after, "Session changes leave both families' awards unchanged");
            }

            yield return Resize(852, 393);
            CheckHomeTargets();
            yield return Capture("play-home-landscape.png");
            yield return CheckDensityInvariant(ui, garden, pet, camera, 852, 393, "landscape");
            yield return OpenSection(ui, garden, "Inbox");
            Check(!garden.TryTapCompanion(CompanionPoint(pet, camera)), "Landscape inbox blocks world touch");
            yield return Capture("play-inbox-landscape.png");
            yield return CloseSection(ui, garden, "Inbox");
            Check(runtimeErrors.Count == 0, "Smoke run contains no runtime errors");
            Finish(true, "");
        }

        private void CheckOwnedModel(CampPrototypeController ui, string appearanceId, AbbyCamp.Presentation.OwnedCompanionKind kind, int creatureId)
        {
            var follower = FindFirstObjectByType<CompanionFollower>();
            Check(ui.HasOwnedCompanionAppearance && ui.DisplayedCreatureKind == kind && ui.DisplayedCreatureId == creatureId
                && follower.Appearance.Definition.AppearanceId == appearanceId && follower.Appearance.Definition.ModelPrefab != null,
                "The saved owned " + kind + " " + creatureId + " uses its exact " + appearanceId + " model");
        }

        private IEnumerator ExerciseCare(CampPrototypeController ui, CampGardenInput garden, AbbyApiClient api,
            int userId, int petId, int mountId, Action<FixtureState> complete)
        {
            FixtureState snapshot = null;
            yield return ReadFixtureState(value => snapshot = value);
            var before = Account(snapshot, userId);
            var otherBefore = Array.Find(snapshot.accounts, account => account.user_id != userId);
            int secondPetId = Array.Find(before.pets, item => item.id != petId).id;
            int expeditionMountId = Array.Find(before.mounts, item => item.id != mountId).id;
            int foodId = before.food[0].item_id;
            Check(before.feed_requests == 0 && before.feed_commits == 0 && Food(before, foodId).quantity == 4
                && Pet(before, petId).growth_points == 75, "Disposable care starts with exact food and growth counters");
            yield return OpenSection(ui, garden, "Bestiary");
            Check(!ui.CareNeedsReview && FindButton("ActiveMount_" + expeditionMountId)?.interactable == false && HasText("Out exploring"),
                "A mount on an expedition cannot be chosen through native care");
            Click("ActivePet_" + secondPetId);
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Active companion save and reload finish");
            yield return ReadFixtureState(value => snapshot = value);
            Check(Pet(Account(snapshot, userId), secondPetId).is_active && !Pet(Account(snapshot, userId), petId).is_active
                && NamedText("ActiveCompanion").Contains("Pip"), "Native companion choice uses server-confirmed active state");
            if (ownedCreatureArt) Check(!ui.HasOwnedCompanionAppearance && HasText("Artwork preview"),
                "An unprepared saved potion variant restores an honest preview instead of recoloring Chick");
            Click("ActiveMount_" + mountId);
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Active mount save and reload finish");
            yield return ReadFixtureState(value => snapshot = value);
            Check(Array.Find(Account(snapshot, userId).mounts, item => item.id == mountId).is_active
                && !Array.Find(Account(snapshot, userId).mounts, item => item.id == expeditionMountId).is_active,
                "Native mount choice changes only the chosen owned mount");
            CheckAwardsUnchanged(new FixtureState { accounts = new[] { before } }, snapshot,
                "Choosing a companion or mount consumes no food and awards no progress");
            Click("ActivePet_" + secondPetId);
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Already-active companion reselection is acknowledged");
            Check(ui.PresentedCompanion.Kind == AbbyCamp.Presentation.OwnedCompanionKind.Pet
                && ui.PresentedCompanion.CreatureId == secondPetId,
                "An explicit already-active pet selection restores companion presentation above the active mount");
            Click("ActiveMount_" + mountId);
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Already-active mount reselection is acknowledged");
            Check(ui.PresentedCompanion.Kind == AbbyCamp.Presentation.OwnedCompanionKind.Mount
                && ui.PresentedCompanion.CreatureId == mountId,
                "An explicit already-active mount selection restores mount presentation above the active pet");
            if (ownedCreatureArt)
            {
                Check(!ui.HasOwnedCompanionAppearance, "An unsupported mount cannot inherit the Bird model");
                Click("ActivePet_" + petId);
                yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Owned Chick companion reselection is acknowledged");
                CheckOwnedModel(ui, "cute-chick", AbbyCamp.Presentation.OwnedCompanionKind.Pet, petId);
            }
            Click("FeedPet_" + petId);
            yield return null;
            Check(NamedText("SheetSubtitle") == "Peep" && NamedText("CareGrowth").Contains("75 / 100"),
                "Care details identify the owned pet and its saved growth");
            CheckRenderedText("CareGrowth");
            Click("Food_" + foodId);
            yield return RevealButton("ConfirmFeedButton");
            yield return Capture("care-food-choice-portrait.png");
            Click("ConfirmFeedButton");
            Check(ui.IsBusy && ui.CareNeedsReview && FindButton("ConfirmFeedButton")?.interactable == false,
                "Care persists its review marker and blocks duplicate taps before dispatch");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "First feed finishes");
            yield return ReadFixtureState(value => snapshot = value);
            var first = Account(snapshot, userId);
            Check(first.feed_requests == 1 && first.feed_commits == 1 && first.inventory_quantity == before.inventory_quantity - 1
                && Food(first, foodId).quantity == 3 && Pet(first, petId).growth_points == 90 && !Pet(first, petId).evolved_to_mount,
                "One feed commits exactly one food and fifteen preferred growth points");
            CheckRewardLedgersUnchanged(before, first, "Feeding does not invent XP, coins or new drops");
            if (ambiguousFeed)
            {
                Check(ui.CareNeedsReview && HasNamed("CareReviewMessage") && FindButton("AcknowledgeCareButton")?.interactable == false
                    && FindButton("Food_" + foodId)?.interactable == false && NamedText("CareGrowth").Contains("75 / 100"),
                    "A lost acknowledgement keeps prior display and blocks care until refreshed and checked");
                if (ownedCreatureArt) CheckOwnedModel(ui, "cute-chick", AbbyCamp.Presentation.OwnedCompanionKind.Pet, petId);
                yield return RevealButton("RefreshCareButton");
                yield return Capture("care-interrupted-portrait.png");
                Click("RefreshCareButton");
                yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Care review refresh finishes");
                Check(ui.CareNeedsReview && NamedText("CareGrowth").Contains("90 / 100") && HasText("3 available")
                    && FindButton("Food_" + foodId)?.interactable == false && FindButton("AcknowledgeCareButton")?.interactable == true,
                    "Refresh reads committed growth and remaining food but still requires explicit acknowledgement");
                yield return ReadFixtureState(value => snapshot = value);
                CheckFeedUnchanged(first, Account(snapshot, userId), "Refreshing uncertain care never posts another feed");
                yield return Capture("care-refreshed-review-portrait.png");
                Click("AcknowledgeCareButton");
                yield return null;
                Check(!ui.CareNeedsReview && FindButton("Food_" + foodId)?.interactable == true,
                    "Explicitly checking fresh creatures and food re-enables a new care action");
                yield return ReadFixtureState(value => snapshot = value);
                CheckFeedUnchanged(first, Account(snapshot, userId), "Care acknowledgement itself consumes nothing");
            }
            Click("Food_" + foodId);
            Click("ConfirmFeedButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Confirmed evolution feed and reload finish");
            yield return ReadFixtureState(value => snapshot = value);
            var evolved = Account(snapshot, userId);
            Check(evolved.feed_requests == 2 && evolved.feed_commits == 2 && Food(evolved, foodId).quantity == 2
                && Pet(evolved, petId).growth_points == 100 && Pet(evolved, petId).evolved_to_mount
                && evolved.mounts.Length == before.mounts.Length + 1 && !ui.CareNeedsReview,
                "A second explicit feed uses one food and the server automatically creates the evolved mount");
            Check(NamedText("BestiaryStatus").Contains("evolved") && NamedText("CareGrowth").Contains("Evolved into a mount")
                && FindButton("ConfirmFeedButton") == null, "Native care recognizes only confirmed evolution and removes feeding");
            CheckRewardLedgersUnchanged(before, evolved, "Evolution changes ownership without extra client awards");
            if (ownedCreatureArt) CheckOwnedModel(ui, "cute-bird", AbbyCamp.Presentation.OwnedCompanionKind.Pet, petId);
            yield return Capture("care-evolved-portrait.png");
            Click("BackCareButton");
            yield return null;
            Check(FindButton("FeedPet_" + petId) == null && FindButton("ActivePet_" + petId) == null,
                "An evolved companion cannot be fed or selected as an unevolved pet");
            foreach (var mount in evolved.mounts) Check(HasNamed("Mount_" + mount.id), "Confirmed mount is present in collection: " + mount.id);
            if (ownedCreatureArt)
            {
                yield return CloseSection(ui, garden, "Bestiary");
                yield return Capture("owned-bird-evolved-home-portrait.png");
                yield return OpenSection(ui, garden, "Bestiary");
                CheckOwnedModel(ui, "cute-bird", AbbyCamp.Presentation.OwnedCompanionKind.Pet, petId);
            }

            Click("FeedPet_" + secondPetId);
            Click("Food_" + foodId);
            using (var arm = UnityWebRequest.Post(fixtureUrl.TrimEnd('/') + "/__fixture/hold-next-care/", "{}", "application/json"))
            {
                yield return arm.SendWebRequest();
                Check(arm.result == UnityWebRequest.Result.Success, "Disposable fixture holds one care acknowledgement until explicit release");
            }
            Click("ConfirmFeedButton");
            float dispatchedDeadline = Time.realtimeSinceStartup + 10;
            do
            {
                yield return ReadFixtureState(value => snapshot = value);
                if (Account(snapshot, userId).care_responses_pending > 0) break;
                yield return null;
            } while (Time.realtimeSinceStartup < dispatchedDeadline);
            var delayed = Account(snapshot, userId);
            Check(delayed.care_responses_pending == 1 && delayed.feed_requests == 3 && delayed.feed_commits == 3
                && delayed.care_hold_timeouts == 0 && ui.IsBusy && ui.CareNeedsReview,
                "Account replacement starts after a real feed commits while its response is still pending; observed pending="
                + delayed.care_responses_pending + ", requests=" + delayed.feed_requests + ", commits=" + delayed.feed_commits
                + ", hold timeouts=" + delayed.care_hold_timeouts + ", busy=" + ui.IsBusy);
            api.ClearSession();
            var clear = typeof(CampPrototypeController).GetMethod("ClearPresentation", BindingFlags.Instance | BindingFlags.NonPublic);
            Check(clear != null, "Native harness can reproduce the browser's presentation clearing on account change");
            clear.Invoke(ui, null);
            yield return null;
            Check(ui.IsDemo && !ui.IsBusy && !ui.IsModalOpen && !HasText("Peep") && !HasText("Pip"),
                "Account change clears pending care controls and the previous account's creature labels");
            Check(!ui.HasOwnedCompanionAppearance && ui.DisplayedCreatureId == 0,
                "Account change clears the old creature model before a delayed acknowledgement arrives");
            yield return Connect(ui, garden, secondUsername, secondPassword);
            Check(api.CurrentUser.id != userId && !ui.CareNeedsReview, "Another family inherits no prior-account care uncertainty");
            yield return OpenSection(ui, garden, "Bestiary");
            Check(NamedText("ActiveCompanion").Contains("Sprout") && !HasNamed("Pet_" + petId) && !HasNamed("Pet_" + secondPetId)
                && !HasText("evolved into a mount!"), "Replacement collection excludes the previous care result");
            yield return ReadFixtureState(value => snapshot = value);
            Check(Account(snapshot, userId).care_responses_pending == 1 && Account(snapshot, userId).care_hold_timeouts == 0,
                "The old care acknowledgement stays held until the replacement account is visibly loaded");
            yield return ReleaseHeldCare();
            float responseDeadline = Time.realtimeSinceStartup + 10;
            do
            {
                yield return ReadFixtureState(value => snapshot = value);
                if (Account(snapshot, userId).care_responses_pending == 0) break;
                yield return null;
            } while (Time.realtimeSinceStartup < responseDeadline);
            Check(Account(snapshot, userId).care_responses_pending == 0 && Account(snapshot, userId).care_hold_timeouts == 0 && !ui.CareNeedsReview && !ui.IsBusy
                && NamedText("ActiveCompanion").Contains("Sprout") && !HasText("Pip"),
                "A delayed old-account response cannot overwrite new labels, controls or review state");
            CheckAwardsUnchanged(new FixtureState { accounts = new[] { otherBefore } }, snapshot,
                "The replacement account's care data remains unchanged");
            CheckFeedUnchanged(otherBefore, Account(snapshot, api.CurrentUser.id), "No care request from the old account reaches the replacement family");
            yield return CloseSection(ui, garden, "Bestiary");
            Click("AccountButton"); yield return null; Click("DisconnectButton"); yield return null;
            yield return Connect(ui, garden, username, password);
            Check(ui.CareNeedsReview, "Returning to the original account retains its interrupted-care marker");
            if (ownedCreatureArt) CheckOwnedModel(ui, "cute-bird", AbbyCamp.Presentation.OwnedCompanionKind.Pet, petId);
            yield return OpenSection(ui, garden, "Bestiary");
            Check(FindButton("FeedPet_" + secondPetId)?.interactable == false && FindButton("AcknowledgeCareButton")?.interactable == true,
                "Fresh original-account history still requires explicit review before more care");
            Click("RefreshCareButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Returning account refresh finishes");
            Click("AcknowledgeCareButton"); yield return null;
            yield return ReadFixtureState(value => snapshot = value);
            var final = Account(snapshot, userId);
            Check(final.feed_requests == 3 && final.feed_commits == 3 && Food(final, foodId).quantity == 1
                && Pet(final, secondPetId).growth_points == 50 && !ui.CareNeedsReview,
                "Reconciliation reads the single interrupted feed and never consumes food again");
            CheckRewardLedgersUnchanged(before, final, "Care and account reconciliation preserve reward ledgers and XP");
            yield return CloseSection(ui, garden, "Bestiary");
            complete(snapshot);
        }

        private IEnumerator ExerciseHatching(CampPrototypeController ui, CampGardenInput garden, AbbyApiClient api,
            int userId, Action<FixtureState> complete)
        {
            FixtureState snapshot = null;
            yield return ReadFixtureState(value => snapshot = value);
            var before = Account(snapshot, userId);
            var otherBefore = Array.Find(snapshot.accounts, account => account.user_id != userId);
            var egg = Array.Find(before.items, item => item.item_type == "egg");
            var potions = Array.FindAll(before.items, item => item.item_type == "potion");
            Check(egg != null && egg.quantity == 3 && potions.Length == 3 && potions[0].quantity == 2
                && potions[1].quantity == 1 && potions[2].quantity == 1 && before.hatch_requests == 0 && before.hatch_commits == 0,
                "Disposable hatching starts with one owned egg stack and three independent potion variants");
            yield return OpenSection(ui, garden, "Bestiary");
            yield return RevealButton("HatcheryButton");
            Click("HatcheryButton");
            yield return WaitUntil(() => ui.HatcheryOpen && !ui.IsBusy && !ui.IsSectionLoading, 5f, "Native hatchery opens without leaving Play");
            Check(HasNamed("Egg_" + egg.item_id) && HasNamed("Potion_" + potions[0].item_id)
                && HasNamed("Potion_" + potions[1].item_id) && HasNamed("Potion_" + potions[2].item_id)
                && FindButton("ConfirmHatchButton") == null, "Hatchery shows owned supplies and requires two explicit choices");
            yield return ReadFixtureState(value => snapshot = value);
            CheckAwardsUnchanged(new FixtureState { accounts = new[] { before, otherBefore } }, snapshot,
                "Opening the native hatchery consumes no items or rewards");
            yield return SelectHatchPair(egg.item_id, potions[0].item_id);
            yield return Capture("hatch-choice-portrait.png");
            Click("ConfirmHatchButton");
            Check(ui.IsBusy && ui.CareNeedsReview && FindButton("ConfirmHatchButton")?.interactable == false,
                "Hatching persists its review marker and blocks duplicate taps before sending the pair");
            Canvas.ForceUpdateCanvases();
            CheckFirstSheetRow("BestiaryStatus", "Confirming from the bottom brings the saving status into the visible viewport");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "First hatch finishes");
            yield return ReadFixtureState(value => snapshot = value);
            var first = Account(snapshot, userId);
            var firstPet = Array.Find(first.pets, item => Array.Find(before.pets, old => old.id == item.id) == null);
            Check(first.hatch_requests == 1 && first.hatch_commits == 1 && first.pets.Length == before.pets.Length + 1
                && firstPet != null && firstPet.growth_points == 0 && !firstPet.is_active && !firstPet.evolved_to_mount
                && ItemQuantity(first, egg.item_id) == 2 && ItemQuantity(first, potions[0].item_id) == 1
                && first.inventory_quantity == before.inventory_quantity - 2,
                "One hatch consumes exactly one egg and one potion and creates one unevolved pet at zero growth");
            CheckRewardLedgersUnchanged(before, first, "Hatching creates no XP, coins or drop rewards");
            if (ambiguousHatch)
            {
                // The snapshot GET above lets the replacement sheet render.
                // Check the visible status before scrolling to any review action.
                Canvas.ForceUpdateCanvases();
                CheckFirstSheetRow("BestiaryStatus", "An interrupted hatch brings its result and next-step status into the visible viewport");
                Check(ui.CareNeedsReview && HasNamed("CareReviewMessage")
                    && FindButton("AcknowledgeCareButton")?.interactable == false
                    && FindButton("Egg_" + egg.item_id)?.interactable == false
                    && !NamedText("BestiaryStatus").Contains("Hatch saved"),
                    "Lost hatch acknowledgement blocks care and does not claim a confirmed reveal");
                yield return Capture("hatch-interrupted-portrait.png");
                yield return CloseSection(ui, garden, "Bestiary");
                yield return OpenSection(ui, garden, "Bestiary");
                Check(ui.CareNeedsReview && HasNamed("Pet_" + firstPet.id)
                    && FindButton("FeedPet_" + firstPet.id)?.interactable == false,
                    "Closing and reopening preserves hatch uncertainty while fresh collection reads show the created pet");
                Click("HatcheryButton");
                yield return null;
                Click("RefreshCareButton");
                yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Interrupted hatch collection and inventory refresh finish");
                Check(ui.HatcheryOpen && ui.CareNeedsReview && FindButton("AcknowledgeCareButton")?.interactable == true
                    && FindButton("Egg_" + egg.item_id)?.interactable == false && HasText("2 available") && HasText("1 available"),
                    "Fresh hatch supplies remain blocked until the child explicitly checks the collection");
                yield return ReadFixtureState(value => snapshot = value);
                CheckHatchUnchanged(first, Account(snapshot, userId), "Reopening and refreshing uncertain hatching never posts another pair");
                yield return RevealButton("AcknowledgeCareButton");
                yield return Capture("hatch-refreshed-review-portrait.png");
                Click("AcknowledgeCareButton"); yield return null;
                Check(!ui.CareNeedsReview && FindButton("Egg_" + egg.item_id)?.interactable == true,
                    "Explicit hatch review enables a new choice after both authoritative reads");
            }
            else
                Check(!ui.CareNeedsReview && NamedText("BestiaryStatus").Contains("Hatch saved"),
                    "Confirmed hatch acknowledges the created pet without leaving an interrupted-action marker");

            yield return SelectHatchPair(egg.item_id, potions[0].item_id);
            Click("ConfirmHatchButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Duplicate hatch is rejected");
            yield return ReadFixtureState(value => snapshot = value);
            var duplicate = Account(snapshot, userId);
            Check(duplicate.hatch_requests == 2 && duplicate.hatch_commits == 1 && duplicate.pets.Length == first.pets.Length
                && duplicate.inventory_quantity == first.inventory_quantity && ItemQuantity(duplicate, egg.item_id) == 2
                && ItemQuantity(duplicate, potions[0].item_id) == 1 && !ui.CareNeedsReview
                && NamedText("BestiaryStatus").Contains("already have") && FindButton("Egg_" + egg.item_id)?.interactable == false,
                "A definite duplicate rejection consumes nothing and requires fresh supplies before another hatch");
            Click("RefreshBestiaryButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Duplicate rejection refresh finishes");
            yield return SelectHatchPair(egg.item_id, potions[1].item_id);
            Click("ConfirmHatchButton");
            Canvas.ForceUpdateCanvases();
            CheckFirstSheetRow("BestiaryStatus", "A new hatch from the bottom keeps its saving status visible");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Second potion hatches a confirmed pet");
            yield return ReadFixtureState(value => snapshot = value);
            var confirmed = Account(snapshot, userId);
            Check(confirmed.hatch_requests == 3 && confirmed.hatch_commits == 2 && confirmed.pets.Length == before.pets.Length + 2
                && ItemQuantity(confirmed, egg.item_id) == 1 && ItemQuantity(confirmed, potions[1].item_id) == 0
                && confirmed.inventory_quantity == before.inventory_quantity - 4 && !ui.CareNeedsReview
                && NamedText("BestiaryStatus").Contains("Hatch saved") && HasText("Twilight Glow")
                && FindButton("Potion_" + potions[1].item_id) == null,
                "Confirmed hatching reveals the server's variant and removes an exhausted potion from choices");
            Canvas.ForceUpdateCanvases();
            CheckFirstSheetRow("BestiaryStatus", "A confirmed hatch brings the saved companion result into the visible viewport");
            CheckRewardLedgersUnchanged(before, confirmed, "Confirmed hatching preserves reward and XP ledgers");
            yield return Capture("hatch-confirmed-portrait.png");
            yield return SelectHatchPair(egg.item_id, potions[2].item_id);
            yield return Resize(852, 393);
            yield return RevealButton("ConfirmHatchButton");
            yield return Capture("hatch-choice-landscape.png");
            yield return Resize(393, 852);
            using (var arm = UnityWebRequest.Post(fixtureUrl.TrimEnd('/') + "/__fixture/hold-next-care/", "{}", "application/json"))
            {
                yield return arm.SendWebRequest();
                Check(arm.result == UnityWebRequest.Result.Success, "Disposable fixture holds one hatch acknowledgement until explicit release");
            }
            Click("ConfirmHatchButton");
            float dispatchedDeadline = Time.realtimeSinceStartup + 10;
            do
            {
                yield return ReadFixtureState(value => snapshot = value);
                if (Account(snapshot, userId).care_responses_pending > 0) break;
                yield return null;
            } while (Time.realtimeSinceStartup < dispatchedDeadline);
            var delayed = Account(snapshot, userId);
            Check(delayed.care_responses_pending == 1 && delayed.hatch_requests == 4 && delayed.hatch_commits == 3
                && delayed.care_hold_timeouts == 0 && ui.IsBusy && ui.CareNeedsReview && ItemQuantity(delayed, egg.item_id) == 0,
                "Account replacement begins after a hatch commits while its acknowledgement is still pending; observed pending="
                + delayed.care_responses_pending + ", requests=" + delayed.hatch_requests + ", commits=" + delayed.hatch_commits
                + ", hold timeouts=" + delayed.care_hold_timeouts + ", busy=" + ui.IsBusy);
            api.ClearSession();
            var clear = typeof(CampPrototypeController).GetMethod("ClearPresentation", BindingFlags.Instance | BindingFlags.NonPublic);
            Check(clear != null, "Hatch harness can reproduce browser presentation clearing on account replacement");
            clear.Invoke(ui, null); yield return null;
            Check(ui.IsDemo && !ui.IsBusy && !ui.IsModalOpen && !ui.HatcheryOpen && !HasText("Moonlit Owl"),
                "Account replacement clears prior hatch choices and confirmation labels");
            yield return Connect(ui, garden, secondUsername, secondPassword);
            Check(api.CurrentUser.id != userId && !ui.CareNeedsReview, "Another family inherits no hatch uncertainty");
            yield return OpenSection(ui, garden, "Bestiary");
            Click("HatcheryButton"); yield return null;
            var otherEgg = Array.Find(otherBefore.items, item => item.item_type == "egg");
            var otherPotion = Array.Find(otherBefore.items, item => item.item_type == "potion");
            Check(ui.HatcheryOpen && FindButton("Egg_" + otherEgg.item_id)?.interactable == true
                && FindButton("Potion_" + otherPotion.item_id)?.interactable == true
                && !HasNamed("Egg_" + egg.item_id) && !HasNamed("Potion_" + potions[0].item_id)
                && FindButton("ConfirmHatchButton") == null && !HasText("Moonlit Owl"),
                "Replacement hatchery contains only its own family's items with no inherited selection");
            yield return ReadFixtureState(value => snapshot = value);
            Check(Account(snapshot, userId).care_responses_pending == 1 && Account(snapshot, userId).care_hold_timeouts == 0,
                "The old hatch acknowledgement stays held until the replacement account and its own supplies are displayed");
            yield return ReleaseHeldCare();
            float responseDeadline = Time.realtimeSinceStartup + 10;
            do
            {
                yield return ReadFixtureState(value => snapshot = value);
                if (Account(snapshot, userId).care_responses_pending == 0) break;
                yield return null;
            } while (Time.realtimeSinceStartup < responseDeadline);
            Check(Account(snapshot, userId).care_responses_pending == 0 && Account(snapshot, userId).care_hold_timeouts == 0 && !ui.IsBusy && !ui.CareNeedsReview
                && ui.HatcheryOpen && !HasText("Starlight Glow") && FindButton("ConfirmHatchButton") == null,
                "A delayed hatch result cannot overwrite replacement-account controls or display an old reveal");
            CheckHatchUnchanged(otherBefore, Account(snapshot, api.CurrentUser.id), "Hatching never changes the replacement family's creatures or items");
            yield return CloseSection(ui, garden, "Bestiary");
            Click("AccountButton"); yield return null; Click("DisconnectButton"); yield return null;
            yield return Connect(ui, garden, username, password);
            Check(ui.CareNeedsReview, "Returning to the original account preserves its interrupted hatch marker");
            yield return OpenSection(ui, garden, "Bestiary");
            Click("HatcheryButton"); yield return null;
            Check(ui.HatcheryOpen && HasNamed("HatchEmptyEggs") && !HasNamedPrefix("Egg_")
                && FindButton("AcknowledgeCareButton")?.interactable == true && FindButton("ConfirmHatchButton") == null,
                "Exhausted eggs are reported from refreshed inventory while interrupted hatching still requires review");
            Click("RefreshCareButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Returning account hatch refresh finishes");
            Click("AcknowledgeCareButton"); yield return null;
            yield return ReadFixtureState(value => snapshot = value);
            var final = Account(snapshot, userId);
            Check(final.hatch_requests == 4 && final.hatch_commits == 3 && final.pets.Length == before.pets.Length + 3
                && final.inventory_quantity == before.inventory_quantity - 6 && ItemQuantity(final, egg.item_id) == 0
                && ItemQuantity(final, potions[0].item_id) == 1 && ItemQuantity(final, potions[1].item_id) == 0
                && ItemQuantity(final, potions[2].item_id) == 0 && !ui.CareNeedsReview,
                "Refresh and acknowledgement reconcile exactly three committed hatches without replaying any pair");
            CheckRewardLedgersUnchanged(before, final, "Hatch reconciliation preserves XP, coins and all reward ledgers");
            Check(final.feed_requests == before.feed_requests && final.feed_commits == before.feed_commits,
                "Hatching never dispatches a feeding action");
            Click("BackHatcheryButton"); yield return null;
            Check(!ui.HatcheryOpen && HasNamed("Pet_" + firstPet.id) && NamedRowCount("Pet_") == final.pets.Length,
                "Returning to creatures shows all server-confirmed hatch identities");
            yield return Capture("hatch-final-collection-portrait.png");
            yield return CloseSection(ui, garden, "Bestiary");
            complete(snapshot);
        }

        private IEnumerator ExerciseExpeditions(CampPrototypeController ui, CampGardenInput garden, AbbyApiClient api,
            int userId, int freeMountId, Action<FixtureState> complete)
        {
            FixtureState snapshot = null;
            yield return ReadFixtureState(value => snapshot = value);
            var before = Account(snapshot, userId);
            var otherBefore = Array.Find(snapshot.accounts, account => account.user_id != userId);
            var ready = Array.Find(before.expeditions, row => row.status == "active" && row.is_ready);
            var cooldown = Array.Find(before.expeditions, row => row.status == "claimed");
            var heldMount = Array.Find(before.mounts, row => row.potion_name == "Peep Trail");
            Check(ready != null && ready.loot.coins == 35 && ready.loot.items.Length == 1 && ready.loot.items[0].quantity == 2
                && cooldown != null && heldMount != null && before.expedition_start_requests == 0 && before.expedition_claim_requests == 0,
                "Disposable expeditions contain free, active, ready and claimed-today mounts with locked payout history");
            yield return OpenSection(ui, garden, "Bestiary");
            yield return RevealButton("ExpeditionsButton");
            Click("ExpeditionsButton"); yield return null;
            Check(ui.ExpeditionsOpen && HasNamed("ViewExpedition_" + ready.id) && HasNamed("ExpeditionMount_" + freeMountId),
                "Mount expeditions open natively with owned free mounts and existing trips");
            yield return ReadFixtureState(value => snapshot = value);
            CheckExpeditionReadUnchanged(before, Account(snapshot, userId), "Opening expeditions starts and claims nothing");
            ApiError problem = null;
            yield return api.StartExpedition(otherBefore.mounts[0].id, "short", _ => { }, error => problem = error);
            Check(problem != null && !problem.OutcomeUnknown, "A foreign mount never passes client ownership eligibility");
            problem = null;
            yield return api.StartExpedition(freeMountId, "marathon", _ => { }, error => problem = error);
            Check(problem != null && !problem.OutcomeUnknown, "An unsupported expedition tier never dispatches");
            yield return PlanExpedition(ui, freeMountId, "short", "2");
            yield return Capture("expedition-start-choice-portrait.png");
            Click("ConfirmExpeditionStartButton");
            Check(ui.IsBusy && ui.CareNeedsReview, "Expedition start persists its marker before dispatch and blocks duplicate taps");
            Canvas.ForceUpdateCanvases();
            CheckFirstSheetRow("BestiaryStatus", "Starting from a scrolled plan brings saving feedback into view");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "First expedition start finishes");
            yield return ReadFixtureState(value => snapshot = value);
            var started = Account(snapshot, userId);
            var trip = Array.Find(started.expeditions, row => row.mount_id == freeMountId && row.status == "active");
            Check(trip != null && trip.tier == "short" && !trip.is_ready && started.expedition_start_requests == 1
                && started.expedition_start_commits == 1 && started.expeditions.Length == before.expeditions.Length + 1,
                "One explicit two-hour choice creates exactly one server-owned expedition");
            CheckExpeditionRewardsUnchanged(before, started, "Starting a trip pays no coins, items, drops or XP");
            if (ambiguousExpeditionStart)
            {
                Check(ui.CareNeedsReview && HasNamed("CareReviewMessage") && FindButton("AcknowledgeCareButton")?.interactable == false,
                    "A lost start response keeps every creature action blocked until complete refresh and review");
                Canvas.ForceUpdateCanvases();
                CheckFirstSheetRow("BestiaryStatus", "An interrupted start keeps its next-step feedback visible");
                yield return Capture("expedition-start-interrupted-portrait.png");
                Click("RefreshCareButton");
                yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Uncertain start collection, items, history and coins refresh finish");
                Check(ui.CareNeedsReview && FindButton("AcknowledgeCareButton")?.interactable == true,
                    "Four complete server reads make expedition review available without replaying start");
                yield return ReadFixtureState(value => snapshot = value);
                CheckExpeditionReadUnchanged(started, Account(snapshot, userId), "Refreshing an uncertain start never sends the mount again");
                yield return RevealButton("AcknowledgeCareButton"); Click("AcknowledgeCareButton"); yield return null;
                Check(!ui.CareNeedsReview, "Explicit expedition review clears only the local uncertainty marker");
            }
            yield return ExpeditionOverview(ui);
            Click("ViewExpedition_" + trip.id); yield return null;
            Check(!api.CanClaimExpedition(trip.id) && FindButton("ConfirmExpeditionClaimButton")?.interactable == false
                && !string.IsNullOrWhiteSpace(NamedText("ExpeditionCountdown")) && !string.IsNullOrWhiteSpace(NamedText("ExpeditionReturnsAt")),
                "An active future trip shows a server countdown and return time while claiming stays disabled");
            problem = null;
            yield return api.ClaimExpedition(trip.id, _ => { }, error => problem = error);
            Check(problem != null && !problem.OutcomeUnknown, "A too-early claim cannot dispatch from a fetched future trip");
            Click("RefreshBestiaryButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Expedition countdown refresh finishes");
            yield return ReadFixtureState(value => snapshot = value);
            CheckExpeditionReadUnchanged(started, Account(snapshot, userId), "Countdown refresh changes no expedition or reward state");
            yield return ExpeditionOverview(ui);
            yield return PlanExpedition(ui, cooldown.mount_id, "short", "2");
            Click("ConfirmExpeditionStartButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Server daily-rest rejection finishes");
            yield return ReadFixtureState(value => snapshot = value);
            var rested = Account(snapshot, userId);
            Check(rested.expedition_start_requests == 2 && rested.expedition_start_commits == 1 && !ui.CareNeedsReview
                && NamedText("BestiaryStatus").Contains("already been out today"),
                "The server rejects a claimed-today mount without inferring the child's local date");
            CheckExpeditionRewardsUnchanged(started, rested, "A daily-rest rejection pays and consumes nothing");
            Click("RefreshBestiaryButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Rejected expedition eligibility refresh finishes");
            yield return ExpeditionOverview(ui);
            Click("ViewExpedition_" + trip.id); yield return null;
            yield return FinishFixtureExpedition(trip.id);
            Check(!api.CanClaimExpedition(trip.id) && FindButton("ConfirmExpeditionClaimButton")?.interactable == false,
                "A changed server return time cannot enable claim before an explicit accepted server refresh");
            Click("RefreshBestiaryButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Ready expedition refresh finishes");
            yield return RevealButton("ConfirmExpeditionClaimButton");
            Click("ConfirmExpeditionClaimButton");
            Check(ui.IsBusy && ui.CareNeedsReview, "Claim persists its marker before dispatch and blocks another payout tap");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "First expedition claim finishes");
            yield return ReadFixtureState(value => snapshot = value);
            var paid = Account(snapshot, userId);
            Check(paid.expedition_claim_requests == 1 && paid.expedition_claim_commits == 1,
                "One explicit ready claim records exactly one materialization");
            CheckExpeditionPayout(rested, paid, trip, "The first claim pays only its locked coins and item slots");
            if (ambiguousExpeditionClaim)
            {
                Check(ui.CareNeedsReview && FindButton("AcknowledgeCareButton")?.interactable == false,
                    "A lost claim acknowledgement preserves uncertainty after the real payout");
                Canvas.ForceUpdateCanvases();
                CheckFirstSheetRow("BestiaryStatus", "An interrupted claim keeps review feedback visible");
                yield return Capture("expedition-claim-interrupted-portrait.png");
                Click("RefreshCareButton");
                yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Uncertain claim balances, inventory and history refresh finish");
                Check(FindButton("AcknowledgeCareButton")?.interactable == true && !api.CanClaimExpedition(trip.id),
                    "Refreshed claimed history and balances enable review while the paid trip stays unclaimable");
                yield return ReadFixtureState(value => snapshot = value);
                CheckExpeditionReadUnchanged(paid, Account(snapshot, userId), "Uncertain claim refresh never repeats the payout");
                yield return RevealButton("AcknowledgeCareButton"); Click("AcknowledgeCareButton"); yield return null;
            }
            problem = null;
            yield return api.ClaimExpedition(trip.id, _ => { }, error => problem = error);
            Check(problem != null && !problem.OutcomeUnknown && FindButton("ConfirmExpeditionClaimButton")?.interactable != true,
                "A claimed trip cannot expose a second enabled claim or dispatch another payout");
            yield return ExpeditionOverview(ui);
            Click("ViewExpedition_" + ready.id); yield return null;
            yield return Resize(852, 393);
            yield return RevealButton("ConfirmExpeditionClaimButton");
            yield return Capture("expedition-ready-claim-landscape.png");
            yield return Resize(393, 852);
            Click("ConfirmExpeditionClaimButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Seeded ready trip confirms its claim");
            yield return ReadFixtureState(value => snapshot = value);
            var confirmed = Account(snapshot, userId);
            Check(confirmed.expedition_claim_requests == 2 && confirmed.expedition_claim_commits == 2 && !ui.CareNeedsReview,
                "A distinct ready trip confirms one new payout without retaining an uncertainty marker");
            CheckExpeditionPayout(paid, confirmed, ready, "Confirmed standard return materializes exactly 35 coins and two keepsakes");
            Canvas.ForceUpdateCanvases();
            CheckFirstSheetRow("BestiaryStatus", "A confirmed claim brings its saved receipt into the visible viewport");
            yield return Capture("expedition-claim-confirmed-portrait.png");
            yield return ExpeditionOverview(ui);
            yield return PlanExpedition(ui, heldMount.id, "long", "8");
            yield return HeldExpeditionAccountReplacement(ui, garden, api, userId, heldMount.id, 0, value => snapshot = value);
            var heldStart = Account(snapshot, userId);
            var heldTrip = Array.Find(heldStart.expeditions, row => row.mount_id == heldMount.id && row.status == "active");
            Check(heldTrip != null && heldTrip.tier == "long" && heldStart.expedition_start_requests == 3
                && heldStart.expedition_start_commits == 2, "Held eight-hour start preserves the exact explicit tier and one saved trip");
            yield return FinishFixtureExpedition(heldTrip.id);
            Click("RefreshBestiaryButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Held trip's ready state refresh finishes");
            yield return ExpeditionOverview(ui); Click("ViewExpedition_" + heldTrip.id); yield return null;
            yield return RevealButton("ConfirmExpeditionClaimButton");
            yield return HeldExpeditionAccountReplacement(ui, garden, api, userId, 0, heldTrip.id, value => snapshot = value);
            var final = Account(snapshot, userId);
            CheckExpeditionPayout(heldStart, final, heldTrip, "A held claim reconciles its single committed payout after account replacement");
            Check(final.expedition_start_requests == 3 && final.expedition_start_commits == 2
                && final.expedition_claim_requests == 3 && final.expedition_claim_commits == 3 && final.care_hold_timeouts == 0,
                "Expedition review and account replacement never replay a start or claim");
            CheckExpeditionReadUnchanged(otherBefore, Account(snapshot, otherBefore.user_id), "All expedition actions preserve the other family's entire history and rewards");
            Click("BackExpeditionCollectionButton"); yield return null;
            Check(!ui.ExpeditionsOpen, "Expeditions return to the native creature collection");
            yield return CloseSection(ui, garden, "Bestiary");
            complete(snapshot);
        }

        private IEnumerator ExpeditionOverview(CampPrototypeController ui)
        {
            if (FindButton("BackExpeditionsButton") != null) Click("BackExpeditionsButton");
            yield return null;
            Check(ui.ExpeditionsOpen, "Trip details return to the native expedition overview");
        }

        private IEnumerator PlanExpedition(CampPrototypeController ui, int mountId, string tier, string hours)
        {
            yield return RevealButton("ExpeditionMount_" + mountId);
            Click("ExpeditionMount_" + mountId); yield return null;
            Check(ui.ExpeditionsOpen && FindButton("ConfirmExpeditionStartButton") == null
                && FindButton("ExpeditionTier_short") != null && FindButton("ExpeditionTier_standard") != null && FindButton("ExpeditionTier_long") != null,
                "An owned free mount requires an explicit choice among all three expedition tiers");
            yield return RevealButton("ExpeditionTier_" + tier); Click("ExpeditionTier_" + tier);
            yield return RevealButton("ConfirmExpeditionStartButton");
            Check(FindButton("ConfirmExpeditionStartButton").GetComponentInChildren<Text>().text.Contains(hours),
                "The start confirmation discloses the selected expedition duration");
        }

        private IEnumerator FinishFixtureExpedition(int expeditionId)
        {
            using (var finish = UnityWebRequest.Post(fixtureUrl.TrimEnd('/') + "/__fixture/finish-expedition/" + expeditionId + "/", "{}", "application/json"))
            {
                finish.timeout = 10;
                yield return finish.SendWebRequest();
                Check(finish.result == UnityWebRequest.Result.Success, "Disposable fixture advances only a designated active expedition's return time");
            }
        }

        private IEnumerator HeldExpeditionAccountReplacement(CampPrototypeController ui, CampGardenInput garden, AbbyApiClient api,
            int userId, int startMountId, int claimId, Action<FixtureState> complete)
        {
            FixtureState snapshot = null;
            yield return ReadFixtureState(value => snapshot = value);
            var before = Account(snapshot, userId);
            var otherBefore = Array.Find(snapshot.accounts, account => account.user_id != userId);
            bool claiming = claimId > 0;
            using (var arm = UnityWebRequest.Post(fixtureUrl.TrimEnd('/') + "/__fixture/hold-next-care/", "{}", "application/json"))
            {
                arm.timeout = 10;
                yield return arm.SendWebRequest();
                Check(arm.result == UnityWebRequest.Result.Success, "Fixture arms an expedition acknowledgement rendezvous");
            }
            Click(claiming ? "ConfirmExpeditionClaimButton" : "ConfirmExpeditionStartButton");
            float observationDeadline = Time.realtimeSinceStartup + 10;
            do
            {
                yield return ReadFixtureState(value => snapshot = value);
                if (Account(snapshot, userId).care_responses_pending == 1) break;
                yield return null;
            } while (Time.realtimeSinceStartup < observationDeadline);
            var committed = Account(snapshot, userId);
            Check(committed.care_responses_pending == 1 && committed.care_hold_timeouts == 0 && ui.IsBusy && ui.CareNeedsReview
                && (claiming ? committed.expedition_claim_commits == before.expedition_claim_commits + 1
                    && Array.Find(committed.expeditions, row => row.id == claimId && row.status == "claimed") != null
                    : committed.expedition_start_commits == before.expedition_start_commits + 1
                    && Array.Find(committed.expeditions, row => row.mount_id == startMountId && row.status == "active") != null),
                "Account replacement observes a real committed expedition " + (claiming ? "claim" : "start")
                + " before acknowledgement; pending=" + committed.care_responses_pending + ", timeouts=" + committed.care_hold_timeouts);
            api.ClearSession();
            var clear = typeof(CampPrototypeController).GetMethod("ClearPresentation", BindingFlags.Instance | BindingFlags.NonPublic);
            Check(clear != null, "Expedition harness can reproduce browser presentation clearing");
            clear.Invoke(ui, null); yield return null;
            Check(ui.IsDemo && !ui.IsBusy && !ui.IsModalOpen && !ui.ExpeditionsOpen,
                "Account replacement clears expedition choices, details and pending controls");
            yield return Connect(ui, garden, secondUsername, secondPassword);
            yield return OpenSection(ui, garden, "Bestiary"); Click("ExpeditionsButton"); yield return null;
            var otherReady = Array.Find(otherBefore.expeditions, row => row.status == "active" && row.is_ready);
            Check(ui.ExpeditionsOpen && !ui.CareNeedsReview && HasNamed("ViewExpedition_" + otherReady.id),
                "Replacement account displays only its own expedition history without inherited uncertainty");
            foreach (var row in committed.expeditions)
                Check(!HasNamed("ViewExpedition_" + row.id), "Previous account expedition is absent: " + row.id);
            Click("ViewExpedition_" + otherReady.id); yield return null;
            yield return ReadFixtureState(value => snapshot = value);
            Check(Account(snapshot, userId).care_responses_pending == 1 && Account(snapshot, userId).care_hold_timeouts == 0
                && HasNamed("ExpeditionStatus_" + otherReady.id),
                "Old expedition acknowledgement remains held until replacement-account details are displayed");
            yield return ReleaseHeldCare();
            float releaseDeadline = Time.realtimeSinceStartup + 10;
            do
            {
                yield return ReadFixtureState(value => snapshot = value);
                if (Account(snapshot, userId).care_responses_pending == 0) break;
                yield return null;
            } while (Time.realtimeSinceStartup < releaseDeadline);
            Check(Account(snapshot, userId).care_responses_pending == 0 && Account(snapshot, userId).care_hold_timeouts == 0
                && !ui.IsBusy && !ui.CareNeedsReview && HasNamed("ExpeditionStatus_" + otherReady.id),
                "Late old-account expedition receipt cannot replace the new account's details or review controls");
            CheckExpeditionReadUnchanged(otherBefore, Account(snapshot, otherBefore.user_id), "Held expedition actions never reach the replacement family");
            yield return CloseSection(ui, garden, "Bestiary");
            Click("AccountButton"); yield return null; Click("DisconnectButton"); yield return null;
            yield return Connect(ui, garden, username, password);
            Check(ui.CareNeedsReview, "Returning to the original account preserves its interrupted expedition marker");
            yield return OpenSection(ui, garden, "Bestiary"); Click("ExpeditionsButton"); yield return null;
            Check(FindButton("AcknowledgeCareButton")?.interactable == true,
                "Complete original-account expedition, inventory, collection and balance reads enable explicit review");
            Click("RefreshCareButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Returning account expedition review refresh finishes");
            yield return RevealButton("AcknowledgeCareButton"); Click("AcknowledgeCareButton"); yield return null;
            yield return ReadFixtureState(value => snapshot = value);
            var after = Account(snapshot, userId);
            CheckExpeditionReadUnchanged(committed, after, "Held expedition refresh and acknowledgement replay neither start nor payout");
            Check(!ui.CareNeedsReview && after.care_hold_timeouts == 0, "Explicit original-account review clears the marker with no hold expiration");
            yield return Capture(claiming ? "expedition-held-claim-reviewed.png" : "expedition-held-start-reviewed.png");
            complete(snapshot);
        }

        private void CheckExpeditionRewardsUnchanged(FixtureAccount before, FixtureAccount after, string label)
        {
            Check(before.inventory_quantity == after.inventory_quantity && before.items.Length == after.items.Length, label);
            foreach (var item in before.items) Check(ItemQuantity(after, item.item_id) == item.quantity, label + ": item " + item.item_id);
            CheckRewardLedgersUnchanged(before, after, label);
        }

        private void CheckExpeditionReadUnchanged(FixtureAccount before, FixtureAccount after, string label)
        {
            Check(before.expedition_start_requests == after.expedition_start_requests && before.expedition_start_commits == after.expedition_start_commits
                && before.expedition_claim_requests == after.expedition_claim_requests && before.expedition_claim_commits == after.expedition_claim_commits
                && before.expeditions.Length == after.expeditions.Length, label);
            foreach (var row in before.expeditions)
            {
                var current = Array.Find(after.expeditions, item => item.id == row.id);
                Check(current != null && current.mount_id == row.mount_id && current.status == row.status && current.tier == row.tier
                    && current.started_at == row.started_at && current.returns_at == row.returns_at && current.claimed_at == row.claimed_at
                    && current.loot.coins == row.loot.coins && current.loot.items.Length == row.loot.items.Length, label + ": trip " + row.id);
                for (int index = 0; index < row.loot.items.Length; index++)
                {
                    var slot = row.loot.items[index];
                    var saved = current.loot.items[index];
                    Check(saved.item_id == slot.item_id && saved.quantity == slot.quantity && saved.name == slot.name
                        && saved.rarity == slot.rarity && saved.item_type == slot.item_type && saved.sprite_key == slot.sprite_key,
                        label + ": locked slot " + row.id + "/" + index);
                }
            }
            Check(before.mounts.Length == after.mounts.Length, label + ": mount collection count");
            foreach (var mount in before.mounts)
            {
                var current = Array.Find(after.mounts, row => row.id == mount.id);
                Check(current != null && current.is_active == mount.is_active && current.potion_name == mount.potion_name,
                    label + ": mount " + mount.id);
            }
            CheckExpeditionRewardsUnchanged(before, after, label);
            CheckHatchUnchanged(before, after, label);
        }

        private void CheckExpeditionPayout(FixtureAccount before, FixtureAccount after, FixtureExpedition trip, string label)
        {
            int quantity = 0;
            var itemTotals = new Dictionary<int, int>();
            foreach (var slot in trip.loot.items)
            {
                quantity += slot.quantity;
                if (!itemTotals.ContainsKey(slot.item_id)) itemTotals.Add(slot.item_id, 0);
                itemTotals[slot.item_id] += slot.quantity;
            }
            Check(after.balance == before.balance + trip.loot.coins && after.inventory_quantity == before.inventory_quantity + quantity
                && after.ledger.Length == before.ledger.Length + 1 && after.ledger[after.ledger.Length - 1].reason == "expedition"
                && after.ledger[after.ledger.Length - 1].amount == trip.loot.coins && after.skill_xp == before.skill_xp
                && EqualIds(after.drop_ids, before.drop_ids), label);
            foreach (var item in itemTotals) Check(ItemQuantity(after, item.Key) == ItemQuantity(before, item.Key) + item.Value,
                label + ": locked item " + item.Key);
            var saved = Array.Find(after.expeditions, row => row.id == trip.id);
            Check(saved != null && saved.status == "claimed" && !string.IsNullOrEmpty(saved.claimed_at), label + ": claimed history is persisted");
        }

        private IEnumerator ReleaseHeldCare()
        {
            using (var release = UnityWebRequest.Post(fixtureUrl.TrimEnd('/') + "/__fixture/release-care/", "{}", "application/json"))
            {
                release.timeout = 10;
                yield return release.SendWebRequest();
                Check(release.result == UnityWebRequest.Result.Success, "The harness explicitly releases the old account's held care acknowledgement");
            }
        }

        private IEnumerator SelectHatchPair(int eggId, int potionId)
        {
            yield return RevealButton("Egg_" + eggId);
            Click("Egg_" + eggId);
            yield return RevealButton("Potion_" + potionId);
            Click("Potion_" + potionId);
            yield return RevealButton("ConfirmHatchButton");
            string label = FindButton("ConfirmHatchButton").GetComponentInChildren<Text>().text;
            Check(label.Contains("1 egg") && label.Contains("1 potion"), "Hatch confirmation discloses consumption of one owned egg and one owned potion");
        }

        private static int ItemQuantity(FixtureAccount account, int id) => Array.Find(account.items, item => item.item_id == id)?.quantity ?? 0;

        private void CheckHatchUnchanged(FixtureAccount before, FixtureAccount after, string label)
        {
            Check(before.hatch_requests == after.hatch_requests && before.hatch_commits == after.hatch_commits
                && before.pets.Length == after.pets.Length && before.items.Length == after.items.Length, label);
            foreach (var item in before.items) Check(ItemQuantity(after, item.item_id) == item.quantity, label + ": item " + item.item_id);
            foreach (var pet in before.pets) Check(Pet(after, pet.id).species_id == pet.species_id && Pet(after, pet.id).potion_id == pet.potion_id
                && Pet(after, pet.id).is_active == pet.is_active, label + ": identity " + pet.id);
            CheckFeedUnchanged(before, after, label);
            CheckRewardLedgersUnchanged(before, after, label);
        }

        private IEnumerator RevealButton(string name)
        {
            yield return null;
            Canvas.ForceUpdateCanvases();
            var button = FindButton(name);
            Check(button != null && button.interactable, "Care action is available: " + name);
            var scroll = button.GetComponentInParent<ScrollRect>();
            Check(scroll != null && scroll.content != null && scroll.viewport != null, "Care actions remain reachable by scrolling");
            var bounds = RectTransformUtility.CalculateRelativeRectTransformBounds(scroll.viewport, button.transform);
            var view = scroll.viewport.rect;
            var position = scroll.content.anchoredPosition;
            if (bounds.min.y < view.yMin + 12) position.y += view.yMin + 12 - bounds.min.y;
            else if (bounds.max.y > view.yMax - 12) position.y -= bounds.max.y - (view.yMax - 12);
            position.y = Mathf.Clamp(position.y, 0, Mathf.Max(0, scroll.content.rect.height - view.height));
            scroll.content.anchoredPosition = position;
            yield return null;
            bounds = RectTransformUtility.CalculateRelativeRectTransformBounds(scroll.viewport, button.transform);
            Check(bounds.size.x >= 43.5f && bounds.size.y >= 43.5f && bounds.min.y >= view.yMin - .5f && bounds.max.y <= view.yMax + .5f,
                "Care action is a visible 44px phone target after scrolling: " + name);
        }

        private static FixturePet Pet(FixtureAccount account, int id) => Array.Find(account.pets, item => item.id == id)
            ?? throw new InvalidOperationException("Fixture pet is missing.");
        private static FixtureFood Food(FixtureAccount account, int id) => Array.Find(account.food, item => item.item_id == id)
            ?? throw new InvalidOperationException("Fixture food is missing.");

        private void CheckFeedUnchanged(FixtureAccount before, FixtureAccount after, string label)
        {
            Check(before.feed_requests == after.feed_requests && before.feed_commits == after.feed_commits
                && before.inventory_quantity == after.inventory_quantity, label);
            foreach (var pet in before.pets) Check(Pet(after, pet.id).growth_points == pet.growth_points
                && Pet(after, pet.id).evolved_to_mount == pet.evolved_to_mount, label + ": pet " + pet.id);
        }

        private void CheckRewardLedgersUnchanged(FixtureAccount before, FixtureAccount after, string label)
        {
            Check(before.balance == after.balance && before.skill_xp == after.skill_xp && EqualIds(before.ledger_ids, after.ledger_ids)
                && EqualIds(before.drop_ids, after.drop_ids), label);
        }

        private IEnumerator Resize(int width, int height)
        {
            Screen.SetResolution(width, height, FullScreenMode.Windowed);
            yield return WaitUntil(() => Screen.width == width && Screen.height == height, 6f, "Viewport resizes to " + width + "x" + height);
            for (int frame = 0; frame < 15; frame++) yield return null;
            Canvas.ForceUpdateCanvases();
        }

        private IEnumerator CheckDensityInvariant(CampPrototypeController ui, CampGardenInput garden,
            CompanionFollower pet, Camera view, int width, int height, string orientation)
        {
            var buttons = new Dictionary<string, Rect>();
            foreach (var name in HomeButtons) buttons.Add(name, LogicalScreenRect(FindButton(name)));
            var title = FindText("CampTitle");
            var titleRect = LogicalScreenRect(title);
            int fontSize = title.fontSize;
            var cameraPosition = view.transform.position;
            var cameraRotation = view.transform.rotation;
            var orthographicSize = view.orthographicSize;
            var anchor = view.WorldToViewportPoint(pet.transform.position + Vector3.up);
            float initialScale = title.GetComponentInParent<Canvas>().scaleFactor;

            yield return Resize(width * 2, height * 2);
            CheckHomeTargets();
            Check(Mathf.Abs(title.GetComponentInParent<Canvas>().scaleFactor / initialScale - 2f) < .01f,
                "Doubling the " + orientation + " framebuffer doubles UI pixel density");
            foreach (var name in HomeButtons)
                Check(RectMatches(buttons[name], LogicalScreenRect(FindButton(name))),
                    "Higher density preserves the logical position and touch size of " + orientation + " " + name);
            Check(title.fontSize == fontSize && RectMatches(titleRect, LogicalScreenRect(title)),
                "Higher density preserves the " + orientation + " title's logical size");
            CheckRenderedText("CampTitle");
            Check(Vector3.Distance(view.transform.position, cameraPosition) < .01f
                && Quaternion.Angle(view.transform.rotation, cameraRotation) < .1f
                && Mathf.Abs(view.orthographicSize - orthographicSize) < .01f
                && Vector3.Distance(view.WorldToViewportPoint(pet.transform.position + Vector3.up), anchor) < .001f,
                "Higher density preserves " + orientation + " companion framing");
            Check(garden.TryTapCompanion(CompanionPoint(pet, view)),
                "Higher density retains the " + orientation + " companion touch hit");
            for (int frame = 0; frame < 15; frame++) yield return null;
            yield return Capture("play-home-" + orientation + "-2x.png");
            yield return OpenSection(ui, garden, "Rewards");
            Check(!garden.TryTapCompanion(CompanionPoint(pet, view)),
                "Higher density keeps " + orientation + " modal controls ahead of companion touch");
            yield return CloseSection(ui, garden, "Rewards");
            yield return Resize(width, height);
            foreach (var name in HomeButtons)
                Check(RectMatches(buttons[name], LogicalScreenRect(FindButton(name))),
                    "Returning to the original density preserves " + orientation + " " + name);
        }

        private IEnumerator CheckKeyboardTargets(CampPrototypeController ui, CampGardenInput garden)
        {
            Click("AccountButton");
            yield return null;
            Check(ui.IsModalOpen && !garden.InputEnabled, "Focused connection controls suspend companion input");
            var input = FindInput("PasswordInput");
            input.ActivateInputField();
            yield return WaitUntil(() => input.isFocused, 3f, "Connection password field receives focus");
            var canvas = input.GetComponentInParent<Canvas>();
            float scale = canvas.scaleFactor;
            var submitRect = LogicalScreenRect(FindButton("ConnectAccountButton"));
            yield return Resize(393, 450);
            Check(input.isFocused && Mathf.Abs(canvas.scaleFactor - scale) < .001f,
                "A keyboard-sized viewport keeps the focused form's original touch scale");
            var resizedSubmit = LogicalScreenRect(FindButton("ConnectAccountButton"));
            Check(Vector2.Distance(resizedSubmit.size, submitRect.size) < .5f && resizedSubmit.height >= 43.5f,
                "Keyboard resizing preserves the connection button's logical touch size");
            var scroll = input.GetComponentInParent<ScrollRect>();
            var bounds = RectTransformUtility.CalculateRelativeRectTransformBounds(scroll.viewport, input.transform);
            var usable = scroll.viewport.rect;
            Check(bounds.min.y >= usable.yMin - .5f && bounds.max.y <= usable.yMax + .5f,
                "Keyboard resizing scrolls the focused password field fully into view");
            input.DeactivateInputField();
            yield return null;
            Check(Mathf.Abs(canvas.scaleFactor - scale) < .001f,
                "Blurring during keyboard dismissal retains the original touch scale");
            yield return Resize(393, 852);
            Click("CancelConnectionButton");
            yield return null;
            Check(!ui.IsModalOpen && garden.InputEnabled, "Dismissing the keyboard form restores companion input");
            CheckHomeTargets();
        }

        private static Rect LogicalScreenRect(Component component)
        {
            if (component == null) throw new InvalidOperationException("Cannot measure a missing UI component.");
            var corners = new Vector3[4];
            ((RectTransform)component.transform).GetWorldCorners(corners);
            var canvas = component.GetComponentInParent<Canvas>();
            var view = canvas.renderMode == RenderMode.ScreenSpaceOverlay ? null : canvas.worldCamera;
            var min = RectTransformUtility.WorldToScreenPoint(view, corners[0]) / canvas.scaleFactor;
            var max = RectTransformUtility.WorldToScreenPoint(view, corners[2]) / canvas.scaleFactor;
            return Rect.MinMaxRect(min.x, min.y, max.x, max.y);
        }

        private static bool RectMatches(Rect expected, Rect actual) =>
            Vector2.Distance(expected.position, actual.position) < .5f && Vector2.Distance(expected.size, actual.size) < .5f;

        private void CheckHomeTargets()
        {
            CheckRenderedText("CampTitle");
            foreach (var name in HomeButtons)
            {
                var button = FindButton(name);
                Check(button != null && button.interactable, "Home action is available: " + name);
                var corners = new Vector3[4];
                ((RectTransform)button.transform).GetWorldCorners(corners);
                var canvas = button.GetComponentInParent<Canvas>();
                var view = canvas.renderMode == RenderMode.ScreenSpaceOverlay ? null : canvas.worldCamera;
                var min = RectTransformUtility.WorldToScreenPoint(view, corners[0]);
                var max = RectTransformUtility.WorldToScreenPoint(view, corners[2]);
                Check((max.x - min.x) / canvas.scaleFactor >= 43.5f && (max.y - min.y) / canvas.scaleFactor >= 43.5f,
                    "Home action has a 44-unit logical touch target: " + name);
                Check(min.x >= -.5f && min.y >= -.5f && max.x <= Screen.width + .5f && max.y <= Screen.height + .5f, "Home action stays in the viewport: " + name);
            }
        }

        private static Vector2 CompanionPoint(CompanionFollower pet, Camera view)
        {
            Renderer largest = null;
            float size = -1f;
            foreach (Transform appearance in pet.Appearance.transform)
            {
                if (appearance.name != "Appearance" || !appearance.gameObject.activeInHierarchy) continue;
                foreach (var renderer in appearance.GetComponentsInChildren<Renderer>())
                {
                    if (!renderer.enabled || !renderer.gameObject.activeInHierarchy) continue;
                    float area = renderer.bounds.size.sqrMagnitude;
                    if (area > size) { largest = renderer; size = area; }
                }
            }
            if (largest == null) throw new InvalidOperationException("Companion has no visible model or portrait bounds.");
            return view.WorldToScreenPoint(largest.bounds.center);
        }

        private void CheckStableWorld(Camera view, CompanionFollower pet, Vector3 cameraPosition, Quaternion cameraRotation, Vector3 petPosition)
        {
            Check(Vector3.Distance(view.transform.position, cameraPosition) < .01f && Quaternion.Angle(view.transform.rotation, cameraRotation) < .1f,
                "Ground taps and greetings keep the camera stable");
            Check(Vector3.Distance(pet.transform.position, petPosition) < .01f, "Greeting animates art without moving the companion home root");
        }

        private IEnumerator OpenSection(CampPrototypeController ui, CampGardenInput garden, string section)
        {
            Click(section + "Button");
            yield return WaitUntil(() => ui.IsModalOpen && !ui.IsBusy && !ui.IsSectionLoading && !ui.IsHomeLoading
                && string.Equals(ui.ActiveSection, section, StringComparison.OrdinalIgnoreCase), 15f, section + " section finishes loading");
            // A successful request can rebuild its sheet during this frame.
            // Wait for the actual Canvas mesh and ScrollRect layout to settle.
            for (int frame = 0; frame < 2; frame++) yield return null;
            Canvas.ForceUpdateCanvases();
            CheckRenderedText("SheetTitle");
            if (!ui.IsDemo)
            {
                CheckFirstSheetRow(section == "Rewards" ? "RewardStatus" : section + "Status");
                if (section == "Rewards") CheckFirstSheetRow("RewardBalance");
            }
            Check(!garden.InputEnabled, section + " modal suspends world input");
        }

        private IEnumerator CloseSection(CampPrototypeController ui, CampGardenInput garden, string section)
        {
            Click("Close" + section + "Button");
            yield return WaitUntil(() => !ui.IsModalOpen, 3f, "Closing " + section + " returns to Play home");
            for (int frame = 0; frame < 2; frame++) yield return null;
            Check(garden.InputEnabled, "Closing a section restores companion touch");
        }

        private IEnumerator Connect(CampPrototypeController ui, CampGardenInput garden, string account, string secret)
        {
            Click("AccountButton");
            yield return null;
            Check(ui.IsModalOpen && !garden.InputEnabled, "Connection form blocks world touch");
            FindInput("ServerAddressInput").text = fixtureUrl;
            FindInput("UsernameInput").text = account;
            FindInput("PasswordInput").text = secret;
            Click("ConnectAccountButton");
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsHomeLoading && !ui.IsModalOpen && !ui.IsDemo, 25f, "Connection and private home reads finish");
            yield return null;
        }

        private IEnumerator ReadFixtureState(Action<FixtureState> success)
        {
            using (var request = UnityWebRequest.Get(fixtureUrl.TrimEnd('/') + "/__fixture/play-state/"))
            {
                request.timeout = 15;
                yield return request.SendWebRequest();
                Check(request.result == UnityWebRequest.Result.Success, "Disposable fixture snapshot read succeeds");
                var state = JsonUtility.FromJson<FixtureState>(request.downloadHandler.text);
                Check(state?.accounts?.Length == 2, "Fixture exposes both throwaway account snapshots");
                success(state);
            }
        }

        private static FixtureAccount Account(FixtureState state, int id)
        {
            var account = Array.Find(state.accounts, item => item.user_id == id);
            return account ?? throw new InvalidOperationException("Fixture account snapshot is missing.");
        }

        private void CheckAwardsUnchanged(FixtureState before, FixtureState after, string label)
        {
            foreach (var original in before.accounts)
            {
                var current = Account(after, original.user_id);
                Check(current.balance == original.balance && current.skill_xp == original.skill_xp && current.inventory_quantity == original.inventory_quantity
                    && EqualIds(current.ledger_ids, original.ledger_ids) && EqualIds(current.drop_ids, original.drop_ids), label);
            }
        }

        private static bool EqualIds(int[] first, int[] second)
        {
            if (first == null || second == null || first.Length != second.Length) return false;
            for (int i = 0; i < first.Length; i++) if (first[i] != second[i]) return false;
            return true;
        }

        private IEnumerator WaitUntil(Func<bool> predicate, float seconds, string label)
        {
            float end = Time.realtimeSinceStartup + seconds;
            while (!predicate() && Time.realtimeSinceStartup < end) yield return null;
            Check(predicate(), label);
        }

        private IEnumerator Capture(string name)
        {
            string path = Path.Combine(output, name);
            yield return CampPreviewCapture.Capture(path, Screen.width, Screen.height);
            Check(File.Exists(path) && new FileInfo(path).Length > 10000, "Rendered screenshot: " + name);
        }

        private void Check(bool condition, string label)
        {
            if (!condition) throw new InvalidOperationException(label);
            checks.Add(label);
        }

        private static string NamedText(string name)
        {
            return FindText(name)?.text ?? "";
        }

        private static Text FindText(string name)
        {
            foreach (var text in FindObjectsByType<Text>(FindObjectsSortMode.None))
                if (text.gameObject.activeInHierarchy && text.name == name) return text;
            return null;
        }

        private void CheckRenderedText(string name)
        {
            var text = FindText(name);
            Check(text != null && !string.IsNullOrWhiteSpace(text.text), "Visible text is present: " + name);
            int vertices = text.cachedTextGenerator.vertexCount;
            Debug.Log($"ABBY_PLAY_TEXT_LAYOUT: {name}; fontSize={text.fontSize}, rect={text.rectTransform.rect}, preferredHeight={text.preferredHeight}, vertices={vertices}.");
            Check(vertices > 4, "Text has rendered glyph geometry: " + name);
        }

        private void CheckFirstSheetRow(string name, string label = null)
        {
            CheckRenderedText(name);
            var text = FindText(name);
            var scroll = text.GetComponentInParent<ScrollRect>();
            Check(scroll != null && scroll.viewport != null && scroll.content != null, "Sheet row has a scroll viewport: " + name);
            var bounds = RectTransformUtility.CalculateRelativeRectTransformBounds(scroll.viewport, text.rectTransform);
            var view = scroll.viewport.rect;
            Debug.Log($"ABBY_PLAY_SHEET_LAYOUT: {name}; rowRect={text.rectTransform.rect}, rowBounds={bounds}, viewport={view}, content={scroll.content.rect}, contentPosition={scroll.content.anchoredPosition}, normalized={scroll.normalizedPosition}.");
            Check(bounds.min.y >= view.yMin - .5f && bounds.max.y <= view.yMax + .5f,
                label ?? "Initial sheet row is fully inside the visible viewport: " + name);
        }

        private static bool HasText(string value)
        {
            foreach (var text in FindObjectsByType<Text>(FindObjectsSortMode.None)) if (text.text.Contains(value)) return true;
            return false;
        }

        private static bool HasNamed(string name)
        {
            foreach (var item in FindObjectsByType<Transform>(FindObjectsSortMode.None)) if (item.gameObject.activeInHierarchy && item.name == name) return true;
            return false;
        }

        private static bool HasNamedPrefix(string prefix) => NamedRows(prefix).Length > 0;

        private static int NamedRowCount(string prefix)
        {
            string rows = NamedRows(prefix);
            return rows.Length == 0 ? 0 : rows.Split('|').Length;
        }

        private static string NamedRows(string prefix)
        {
            var names = new List<string>();
            foreach (var item in FindObjectsByType<Transform>(FindObjectsSortMode.None))
                if (item.gameObject.activeInHierarchy && item.name.StartsWith(prefix, StringComparison.Ordinal)) names.Add(item.name);
            names.Sort(StringComparer.Ordinal);
            return string.Join("|", names);
        }

        private static InputField FindInput(string name)
        {
            foreach (var input in FindObjectsByType<InputField>(FindObjectsSortMode.None)) if (input.name == name) return input;
            throw new InvalidOperationException("Input not found: " + name);
        }

        private static void Click(string name)
        {
            var button = FindButton(name);
            if (button == null || !button.interactable) throw new InvalidOperationException("Unavailable button: " + name);
            button.onClick.Invoke();
        }

        private static Button FindButton(string name)
        {
            foreach (var button in FindObjectsByType<Button>(FindObjectsSortMode.None)) if (button.gameObject.activeInHierarchy && button.name == name) return button;
            return null;
        }

        private void Finish(bool success, string detail)
        {
            failed = !success;
            Application.logMessageReceived -= ObserveLog;
            File.WriteAllText(Path.Combine(output, "smoke-results.txt"), (success ? "PASSED" : "FAILED") + "\n"
                + string.Join("\n", checks) + "\n" + detail + "\n" + string.Join("\n", runtimeErrors));
            Debug.Log("ABBY_CAMP_RUNTIME_SMOKE_" + (success ? "PASSED" : "FAILED") + ": " + checks.Count + " checks.");
            Application.Quit(success ? 0 : 1);
        }
    }
}
#endif
