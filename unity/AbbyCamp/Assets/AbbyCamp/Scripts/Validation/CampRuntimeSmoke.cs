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
        private bool failed, failFirstMarkRead, ambiguousFeed;
        private string output, fixtureUrl, username, password, secondUsername, secondPassword;

        [Serializable] private sealed class FixtureState { public FixtureAccount[] accounts; }
        [Serializable] private sealed class FixtureAccount
        {
            public int user_id, balance, inventory_quantity, skill_xp, notification_count;
            public int feed_requests, feed_commits, care_responses_pending;
            public int[] ledger_ids, drop_ids, unread_ids;
            public FixturePet[] pets;
            public FixtureMount[] mounts;
            public FixtureFood[] food;
        }
        [Serializable] private sealed class FixturePet { public int id, growth_points; public bool is_active, evolved_to_mount; }
        [Serializable] private sealed class FixtureMount { public int id; public bool is_active; }
        [Serializable] private sealed class FixtureFood { public int item_id, quantity; }

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
                Check(stable != null && stable.pets.Length == 2 && stable.mounts.Length == 2 && stable.pets[0].name == "Peep",
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
                Check(NamedText("CompanionName") == "Meadow friend" && HasText("Artwork preview") && NamedText("CoinsBalance").Contains(initial.balance.ToString()),
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
                Click("AccountButton");
                yield return null;
                Click("DisconnectButton");
                yield return WaitUntil(() => ui.IsDemo && !ui.IsModalOpen && !ui.IsHomeLoading, 10f, "Disconnect clears the private home");
                Check(!api.IsAuthenticated && !HasText("Active: Peep") && !HasNamedPrefix("Notification_")
                    && !HasNamedPrefix("Pet_") && !HasNamedPrefix("Mount_"), "Disconnect clears old private labels and rows");
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
            Click("ActiveMount_" + mountId);
            yield return WaitUntil(() => !ui.IsBusy && !ui.IsSectionLoading, 15f, "Active mount save and reload finish");
            yield return ReadFixtureState(value => snapshot = value);
            Check(Array.Find(Account(snapshot, userId).mounts, item => item.id == mountId).is_active
                && !Array.Find(Account(snapshot, userId).mounts, item => item.id == expeditionMountId).is_active,
                "Native mount choice changes only the chosen owned mount");
            CheckAwardsUnchanged(new FixtureState { accounts = new[] { before } }, snapshot,
                "Choosing a companion or mount consumes no food and awards no progress");
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
            yield return Capture("care-evolved-portrait.png");
            Click("BackCareButton");
            yield return null;
            Check(FindButton("FeedPet_" + petId) == null && FindButton("ActivePet_" + petId) == null,
                "An evolved companion cannot be fed or selected as an unevolved pet");
            foreach (var mount in evolved.mounts) Check(HasNamed("Mount_" + mount.id), "Confirmed mount is present in collection: " + mount.id);

            Click("FeedPet_" + secondPetId);
            Click("Food_" + foodId);
            using (var arm = UnityWebRequest.Post(fixtureUrl.TrimEnd('/') + "/__fixture/delay-next-care/", "{}", "application/json"))
            {
                yield return arm.SendWebRequest();
                Check(arm.result == UnityWebRequest.Result.Success, "Disposable fixture arms one delayed care acknowledgement");
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
                && ui.IsBusy && ui.CareNeedsReview, "Account replacement starts after a real feed commits while its response is still pending");
            api.ClearSession();
            var clear = typeof(CampPrototypeController).GetMethod("ClearPresentation", BindingFlags.Instance | BindingFlags.NonPublic);
            Check(clear != null, "Native harness can reproduce the browser's presentation clearing on account change");
            clear.Invoke(ui, null);
            yield return null;
            Check(ui.IsDemo && !ui.IsBusy && !ui.IsModalOpen && !HasText("Peep") && !HasText("Pip"),
                "Account change clears pending care controls and the previous account's creature labels");
            yield return Connect(ui, garden, secondUsername, secondPassword);
            Check(api.CurrentUser.id != userId && !ui.CareNeedsReview, "Another family inherits no prior-account care uncertainty");
            yield return OpenSection(ui, garden, "Bestiary");
            Check(NamedText("ActiveCompanion").Contains("Sprout") && !HasNamed("Pet_" + petId) && !HasNamed("Pet_" + secondPetId)
                && !HasText("evolved into a mount!"), "Replacement collection excludes the previous care result");
            float responseDeadline = Time.realtimeSinceStartup + 10;
            do
            {
                yield return ReadFixtureState(value => snapshot = value);
                if (Account(snapshot, userId).care_responses_pending == 0) break;
                yield return null;
            } while (Time.realtimeSinceStartup < responseDeadline);
            Check(Account(snapshot, userId).care_responses_pending == 0 && !ui.CareNeedsReview && !ui.IsBusy
                && NamedText("ActiveCompanion").Contains("Sprout") && !HasText("Pip"),
                "A delayed old-account response cannot overwrite new labels, controls or review state");
            CheckAwardsUnchanged(new FixtureState { accounts = new[] { otherBefore } }, snapshot,
                "The replacement account's care data remains unchanged");
            CheckFeedUnchanged(otherBefore, Account(snapshot, api.CurrentUser.id), "No care request from the old account reaches the replacement family");
            yield return CloseSection(ui, garden, "Bestiary");
            Click("AccountButton"); yield return null; Click("DisconnectButton"); yield return null;
            yield return Connect(ui, garden, username, password);
            Check(ui.CareNeedsReview, "Returning to the original account retains its interrupted-care marker");
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

        private void CheckFirstSheetRow(string name)
        {
            CheckRenderedText(name);
            var text = FindText(name);
            var scroll = text.GetComponentInParent<ScrollRect>();
            Check(scroll != null && scroll.viewport != null && scroll.content != null, "Sheet row has a scroll viewport: " + name);
            var bounds = RectTransformUtility.CalculateRelativeRectTransformBounds(scroll.viewport, text.rectTransform);
            var view = scroll.viewport.rect;
            Debug.Log($"ABBY_PLAY_SHEET_LAYOUT: {name}; rowRect={text.rectTransform.rect}, rowBounds={bounds}, viewport={view}, content={scroll.content.rect}, contentPosition={scroll.content.anchoredPosition}, normalized={scroll.normalizedPosition}.");
            Check(bounds.min.y >= view.yMin - .5f && bounds.max.y <= view.yMax + .5f,
                "Initial sheet row is fully inside the visible viewport: " + name);
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
