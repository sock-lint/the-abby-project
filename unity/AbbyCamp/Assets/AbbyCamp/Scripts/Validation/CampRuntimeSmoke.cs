#if UNITY_EDITOR || DEVELOPMENT_BUILD
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
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
    /// greetings must not award anything; inbox mutations require confirmation.</summary>
    public sealed class CampRuntimeSmoke : MonoBehaviour
    {
        private static readonly string[] HomeButtons = {
            "RewardsButton", "InboxButton", "BestiaryButton", "JournalButton",
            "GradesButton", "TasksButton", "PatCompanionButton", "AccountButton", "TodayButton"
        };
        private readonly List<string> checks = new List<string>();
        private readonly List<string> runtimeErrors = new List<string>();
        private bool failed, failFirstMarkRead;
        private string output, fixtureUrl, username, password, secondUsername, secondPassword;

        [Serializable] private sealed class FixtureState { public FixtureAccount[] accounts; }
        [Serializable] private sealed class FixtureAccount
        {
            public int user_id, balance, inventory_quantity, skill_xp, notification_count;
            public int[] ledger_ids, drop_ids, unread_ids;
        }

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
                Check(stable != null && stable.pets.Length == 1 && stable.mounts.Length == 1 && stable.pets[0].name == "Peep",
                    "The server returns the child's real owned pet and mount");
                int primaryPet = stable.pets[0].id, primaryMount = stable.mounts[0].id;
                Check(NamedText("CompanionName") == "Meadow friend" && HasText("Bird artwork preview") && NamedText("CoinsBalance").Contains(initial.balance.ToString()),
                    "Home reports saved coins while honestly labeling the bird artwork preview");
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
                Check(problem == null && notices != null && notices.count == initial.notification_count && notices.count > 20 && !string.IsNullOrEmpty(notices.next),
                    "Inbox uses actual paginated history with more than twenty saved notifications");
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
                Check(NamedRows("Notification_") != firstRows && NamedText("UnreadCount") == unreadLabel, "Next page changes displayed IDs without clearing global unread count");
                yield return Capture("connected-inbox-next-page-portrait.png");
                Click("PreviousInboxPageButton");
                yield return WaitUntil(() => !ui.IsSectionLoading && !ui.IsBusy, 15f, "Previous inbox page finishes");
                Check(NamedRows("Notification_") == firstRows && NamedText("UnreadCount") == unreadLabel, "Previous page restores its rows and preserves unread count");
                yield return CloseSection(ui, garden, "Inbox");
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
                Check(NamedText("CompanionName") == "Meadow friend" && HasText("Bird artwork preview") && !HasText("Peep"),
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
            yield return OpenSection(ui, garden, "Inbox");
            Check(!garden.TryTapCompanion(CompanionPoint(pet, camera)), "Landscape inbox blocks world touch");
            yield return Capture("play-inbox-landscape.png");
            yield return CloseSection(ui, garden, "Inbox");
            Check(runtimeErrors.Count == 0, "Smoke run contains no runtime errors");
            Finish(true, "");
        }

        private IEnumerator Resize(int width, int height)
        {
            Screen.SetResolution(width, height, FullScreenMode.Windowed);
            yield return WaitUntil(() => Screen.width == width && Screen.height == height, 6f, "Viewport resizes to " + width + "x" + height);
            for (int frame = 0; frame < 15; frame++) yield return null;
            Canvas.ForceUpdateCanvases();
        }

        private void CheckHomeTargets()
        {
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
                Check(max.x - min.x >= 43.5f && max.y - min.y >= 43.5f, "Home action has a 44px touch target: " + name);
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
            foreach (var text in FindObjectsByType<Text>(FindObjectsSortMode.None)) if (text.name == name) return text.text;
            return "";
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
