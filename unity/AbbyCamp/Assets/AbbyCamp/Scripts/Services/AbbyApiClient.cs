using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Runtime.InteropServices;
using AbbyCamp.Data;
using UnityEngine;
using UnityEngine.Networking;

namespace AbbyCamp.Services
{
    /// <summary>
    /// Coroutine client for the existing Django API. Call these methods through
    /// StartCoroutine; each invokes exactly one success or failure callback while
    /// its coroutine remains alive. Session credentials exist only in memory.
    /// No request is retried automatically, including a failed mutation.
    /// </summary>
    public sealed class AbbyApiClient : MonoBehaviour
    {
        [SerializeField] private string baseUrl = "http://127.0.0.1:8000";
        [SerializeField, Range(5, 60)] private int timeoutSeconds = 20;

        private string token;
        private string configurationError;
        private int sessionVersion;
        private string readNamespace = Guid.NewGuid().ToString("N");
        private bool loginInFlight;
        private string browserOrigin;
        private string observedBrowserToken;
        private readonly HashSet<UnityWebRequest> activeRequests = new HashSet<UnityWebRequest>();
        private readonly Dictionary<int, HabitDto> knownHabits = new Dictionary<int, HabitDto>();
        private readonly HashSet<int> knownNotifications = new HashSet<int>();

        public string BaseUrl => baseUrl;
        public UserDto CurrentUser { get; private set; }
        public bool IsAuthenticated => !string.IsNullOrEmpty(token) && CurrentUser != null;
        public bool MutationInFlight { get; private set; }
        public bool SessionTransitionInFlight => loginInFlight || MutationInFlight;
        public event Action BrowserSessionChanged;

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] private static extern string AbbySession_ReadToken();
        [DllImport("__Internal")] private static extern void AbbySession_ClearToken(string expectedToken);
        [DllImport("__Internal")] private static extern void AbbySession_OpenJournal();
        [DllImport("__Internal")] private static extern int AbbySession_OpenDestination(string path);
#endif

        [Serializable] private sealed class LoginBody
        {
            public string action = "login";
            public string username;
            public string password;
        }

        [Serializable] private sealed class TapBody { public int direction = 1; }

        private void Awake()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            // A /play/ build connects to the same origin as the web app and API.
            // Never default a phone browser to the developer PC's loopback server.
            if (Uri.TryCreate(Application.absoluteURL, UriKind.Absolute, out var page))
                baseUrl = browserOrigin = page.GetLeftPart(UriPartial.Authority);
#endif
            if (!ConfigureBaseUrl(baseUrl, out var error)) configurationError = error;
#if UNITY_WEBGL && !UNITY_EDITOR
            observedBrowserToken = AbbySession_ReadToken() ?? "";
#endif
        }

        private void OnDestroy() => ClearSession();

        private void Update() => SynchronizeBrowserSession();

        // Read again before every request and after every response as well as
        // during play. Background tabs may pause Update while the journal logs
        // out or switches account. Never accept an old response into a new session.
        private bool SynchronizeBrowserSession()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            string current = AbbySession_ReadToken() ?? "";
            if (!string.Equals(observedBrowserToken, current, StringComparison.Ordinal))
            {
                observedBrowserToken = current;
                ClearSession();
                BrowserSessionChanged?.Invoke();
                return true;
            }
#endif
            return false;
        }

        public void OpenJournal()
        {
            OpenDestination(PlayDestination.Journal);
        }

        public bool OpenDestination(PlayDestination destination)
        {
            string path = DestinationPath(destination);
            if (path == null || !TryValidateBaseUrl(baseUrl, out var origin, out _)) return false;
#if UNITY_WEBGL && !UNITY_EDITOR
            return AbbySession_OpenDestination(path) == 1;
#else
            Application.OpenURL(origin + path);
            return true;
#endif
        }

        public bool OpenNotificationDestination(NotificationDto notification)
        {
            return notification != null && TryResolveNotificationDestination(notification.link, notification.notification_type, out var destination)
                && OpenDestination(destination);
        }

        public static string DestinationPath(PlayDestination destination)
        {
            switch (destination)
            {
                case PlayDestination.Today: return "/";
                case PlayDestination.Journal: return "/chronicle?tab=journal";
                case PlayDestination.Grades: return "/chronicle?tab=grades";
                case PlayDestination.Tasks: return "/quests";
                case PlayDestination.RewardShop: return "/treasury?tab=bazaar";
                case PlayDestination.Satchel: return "/treasury?tab=satchel";
                case PlayDestination.Bestiary: return "/bestiary";
                case PlayDestination.BestiaryHatchery: return "/bestiary?tab=hatchery";
                case PlayDestination.BestiaryCompanions: return "/bestiary?tab=companions";
                case PlayDestination.BestiaryMounts: return "/bestiary?tab=mounts";
                case PlayDestination.BestiaryCodex: return "/bestiary?tab=codex";
                case PlayDestination.TasksStudy: return "/quests?tab=study";
                case PlayDestination.TasksDuties: return "/quests?tab=duties";
                case PlayDestination.TasksRituals: return "/quests?tab=rituals";
                case PlayDestination.TasksMovement: return "/quests?tab=movement";
                case PlayDestination.TasksVentures: return "/quests?tab=ventures";
                case PlayDestination.TasksForge: return "/quests?tab=forge";
                case PlayDestination.TasksTrials: return "/quests?tab=trials";
                case PlayDestination.Skills: return "/atlas?tab=skills";
                case PlayDestination.Badges: return "/atlas?tab=badges";
                case PlayDestination.Lorebook: return "/atlas?tab=lorebook";
                case PlayDestination.Character: return "/sigil";
                case PlayDestination.Yearbook: return "/chronicle?tab=yearbook";
                case PlayDestination.Creations: return "/chronicle?tab=sketchbook";
                case PlayDestination.Wages: return "/treasury?tab=wages";
                case PlayDestination.Coffers: return "/treasury?tab=coffers";
                case PlayDestination.Savings: return "/treasury?tab=hoards";
                default: return null;
            }
        }

        /// <summary>Only a known typed destination is returned. Raw URLs, query
        /// strings and identifiers from notifications are never forwarded.</summary>
        public static bool TryResolveNotificationDestination(string link, string notificationType, out PlayDestination destination)
        {
            if (TryResolveNotificationLink(link, out destination)) return true;
            destination = PlayDestination.Today;
            string type = notificationType ?? "";
            switch (type)
            {
                case "journal_reply": case "chronicle_first_ever": destination = PlayDestination.Journal; return true;
                case "birthday": destination = PlayDestination.Yearbook; return true;
                case "drop_received": destination = PlayDestination.Satchel; return true;
                case "pet_evolved": case "expedition_returned": destination = PlayDestination.BestiaryMounts; return true;
                case "mount_bred": destination = PlayDestination.BestiaryHatchery; return true;
                case "companion_growth": destination = PlayDestination.BestiaryCompanions; return true;
                case "badge_earned": destination = PlayDestination.Badges; return true;
                case "skill_unlocked": destination = PlayDestination.Skills; return true;
                case "milestone_completed": destination = PlayDestination.TasksVentures; return true;
                case "timecard_ready": case "timecard_approved": destination = PlayDestination.Wages; return true;
                case "payout_recorded": destination = PlayDestination.Coffers; return true;
                case "savings_goal_completed": destination = PlayDestination.Savings; return true;
                case "quest_completed": case "comeback_suggested": destination = PlayDestination.TasksTrials; return true;
                case "streak_milestone": case "streak_at_risk": case "perfect_day": case "daily_check_in": destination = PlayDestination.Today; return true;
            }
            if (type.StartsWith("redemption_", StringComparison.Ordinal) || type.StartsWith("exchange_", StringComparison.Ordinal)
                || type == "low_reward_stock" || type == "reward_restocked") destination = PlayDestination.RewardShop;
            else if (type.StartsWith("homework_", StringComparison.Ordinal)) destination = PlayDestination.TasksStudy;
            else if (type.StartsWith("chore_", StringComparison.Ordinal)) destination = PlayDestination.TasksDuties;
            else if (type.StartsWith("habit_", StringComparison.Ordinal)) destination = PlayDestination.TasksRituals;
            else if (type.StartsWith("project_", StringComparison.Ordinal)) destination = PlayDestination.TasksVentures;
            else if (type.StartsWith("print_", StringComparison.Ordinal)) destination = PlayDestination.TasksForge;
            else if (type.StartsWith("creation_", StringComparison.Ordinal)) destination = PlayDestination.Creations;
            else return false;
            return true;
        }

        private static bool TryResolveNotificationLink(string link, out PlayDestination destination)
        {
            destination = PlayDestination.Today;
            if (string.IsNullOrEmpty(link) || link.Length > 512 || link[0] != '/' || link.StartsWith("//", StringComparison.Ordinal)) return false;
            foreach (char character in link)
                if (char.IsWhiteSpace(character) || char.IsControl(character) || character == '\\' || character == '%' || character == '#') return false;
            foreach (PlayDestination candidate in Enum.GetValues(typeof(PlayDestination)))
                if (link == DestinationPath(candidate)) { destination = candidate; return true; }
            switch (link)
            {
                case "/journal": destination = PlayDestination.Journal; return true;
                case "/grades": destination = PlayDestination.Grades; return true;
                case "/tasks": destination = PlayDestination.Tasks; return true;
                case "/homework": destination = PlayDestination.TasksStudy; return true;
                case "/chores": destination = PlayDestination.TasksDuties; return true;
                case "/habits": destination = PlayDestination.TasksRituals; return true;
                case "/movement": destination = PlayDestination.TasksMovement; return true;
                case "/projects": destination = PlayDestination.TasksVentures; return true;
                case "/trials": case "/quests/trials": destination = PlayDestination.TasksTrials; return true;
                case "/rewards": destination = PlayDestination.RewardShop; return true;
                case "/inventory": destination = PlayDestination.Satchel; return true;
                case "/stable": destination = PlayDestination.BestiaryCompanions; return true;
                case "/character": destination = PlayDestination.Character; return true;
                case "/achievements": case "/atlas": destination = PlayDestination.Skills; return true;
                case "/lorebook": destination = PlayDestination.Lorebook; return true;
                case "/yearbook": case "/atlas?tab=yearbook": destination = PlayDestination.Yearbook; return true;
                case "/portfolio": case "/sketchbook": case "/chronicle": case "/atlas?tab=sketchbook": destination = PlayDestination.Creations; return true;
                case "/timecards": destination = PlayDestination.Wages; return true;
                case "/payments": case "/treasury": destination = PlayDestination.Coffers; return true;
            }
            // Legacy project-detail links resolve to the existing task tab. An
            // arbitrary path/query still cannot cross the bridge.
            foreach (string prefix in new[] { "/projects/", "/quests/ventures/" })
                if (link.StartsWith(prefix, StringComparison.Ordinal) && int.TryParse(link.Substring(prefix.Length), NumberStyles.None, CultureInfo.InvariantCulture, out var id) && id > 0)
                { destination = PlayDestination.TasksVentures; return true; }
            return false;
        }

        /// <summary>Web only: validate the journal's existing same-origin token
        /// using /me. No password login, token minting, or mutation is performed.
        /// Parent sessions remain available to the journal, not camp actions.</summary>
        public IEnumerator ResumeBrowserSession(Action<UserDto> success, Action<ApiError> failure)
        {
            SynchronizeBrowserSession();
            if (loginInFlight || MutationInFlight)
            {
                failure?.Invoke(new ApiError("Wait for the current action to finish before connecting."));
                yield break;
            }
            ClearSession();
            if (string.IsNullOrEmpty(observedBrowserToken))
            {
                failure?.Invoke(new ApiError("Sign in in your journal, then return to your world.", requiresLogin: true));
                yield break;
            }
            token = observedBrowserToken;
            loginInFlight = true;
            try
            {
                yield return Send("GET", baseUrl + "/api/auth/me/", null, true, false, json =>
                {
                    UserDto user;
                    try { user = ApiContract.ParseUser(json); }
                    catch (Exception exception)
                    {
                        ClearSession();
                        failure?.Invoke(InvalidResponse(exception, false));
                        return;
                    }
                    if (user.role != "child")
                    {
                        ClearSession();
                        failure?.Invoke(new ApiError("This world uses a child account. Parent tools are in the journal."));
                        return;
                    }
                    CurrentUser = user;
                    success?.Invoke(user);
                }, problem => { ClearSession(); failure?.Invoke(problem); }, validatingSession: true);
            }
            finally { loginInFlight = false; }
        }

        /// <summary>Accepts an origin such as https://abby.example.com. Plain HTTP
        /// is allowed only for loopback development. Changing origin ends session.</summary>
        public bool ConfigureBaseUrl(string value, out string error)
        {
            if (!TryValidateBaseUrl(value, out var origin, out error)) return false;
#if UNITY_WEBGL && !UNITY_EDITOR
            if (!string.Equals(origin, browserOrigin, StringComparison.Ordinal))
            {
                error = "Open your world from the same address as your journal.";
                return false;
            }
#endif
            if (!string.Equals(baseUrl, origin, StringComparison.Ordinal) || configurationError != null)
                ClearSession();
            baseUrl = origin;
            configurationError = null;
            return true;
        }

        public static bool TryValidateBaseUrl(string value, out string origin, out string error)
        {
            origin = null;
            error = "Use a server origin such as https://abby.example.com or http://127.0.0.1:8000.";
            if (!Uri.TryCreate(value == null ? null : value.Trim(), UriKind.Absolute, out var uri)) return false;
            if ((uri.Scheme != Uri.UriSchemeHttps && uri.Scheme != Uri.UriSchemeHttp) ||
                !string.IsNullOrEmpty(uri.UserInfo) || !string.IsNullOrEmpty(uri.Query) ||
                !string.IsNullOrEmpty(uri.Fragment) || uri.AbsolutePath != "/" || string.IsNullOrEmpty(uri.Host)) return false;
            if (uri.Scheme == Uri.UriSchemeHttp && !uri.IsLoopback)
            {
                error = "Use HTTPS for a remote server. HTTP is supported only on this computer's loopback address.";
                return false;
            }
            origin = uri.GetLeftPart(UriPartial.Authority);
            error = null;
            return true;
        }

        /// <summary>Clears the local session without revoking Django tokens in
        /// other clients. Any active network requests are aborted. Aborting a tap
        /// cannot undo a tap already committed by the server.</summary>
        public void ClearSession()
        {
            sessionVersion++;
            readNamespace = Guid.NewGuid().ToString("N");
            token = null;
            CurrentUser = null;
            knownHabits.Clear();
            knownNotifications.Clear();
            foreach (var request in activeRequests) request.Abort();
        }

        /// <summary>Separates private GETs from an older service worker's API
        /// cache. The random namespace stays in memory for this session and
        /// contains no credential. Pagination may carry an older namespace;
        /// replace every copy while preserving other query parameters.</summary>
        public string BuildReadUrl(string url)
        {
            var builder = new UriBuilder(url);
            var parameters = new List<string>();
            foreach (var parameter in builder.Query.TrimStart('?').Split('&'))
            {
                if (parameter.Length == 0) continue;
                int separator = parameter.IndexOf('=');
                string key = separator < 0 ? parameter : parameter.Substring(0, separator);
                if (Uri.UnescapeDataString(key.Replace("+", " ")) == "_abby_session") continue;
                parameters.Add(parameter);
            }
            parameters.Add("_abby_session=" + readNamespace);
            builder.Query = string.Join("&", parameters);
            return builder.Uri.AbsoluteUri;
        }

        public IEnumerator Login(string username, string password, Action<UserDto> success, Action<ApiError> failure)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            failure?.Invoke(new ApiError("Sign in in your journal, then return to your world.", requiresLogin: true));
            yield break;
#else
            if (loginInFlight || MutationInFlight)
            {
                failure?.Invoke(new ApiError("Wait for the current action to finish before signing in."));
                yield break;
            }
            if (string.IsNullOrWhiteSpace(username) || string.IsNullOrEmpty(password))
            {
                failure?.Invoke(new ApiError("Enter your username and password."));
                yield break;
            }
            ClearSession();
            loginInFlight = true;
            try
            {
                var body = JsonUtility.ToJson(new LoginBody { username = username.Trim(), password = password });
                yield return Send("POST", baseUrl + "/api/auth/", body, false, false, json =>
                {
                    try
                    {
                        var user = ApiContract.ParseLogin(json, out var sessionToken);
                        token = sessionToken;
                        CurrentUser = user;
                    }
                    catch (Exception exception)
                    {
                        failure?.Invoke(InvalidResponse(exception, false));
                        return;
                    }
                    success?.Invoke(CurrentUser);
                }, failure);
            }
            finally { loginInFlight = false; }
#endif
        }

        public IEnumerator FetchMe(Action<UserDto> success, Action<ApiError> failure)
        {
            yield return Send("GET", baseUrl + "/api/auth/me/", null, true, false, json =>
            {
                UserDto user;
                try
                {
                    user = ApiContract.ParseUser(json);
                    if (CurrentUser != null && user.id != CurrentUser.id)
                        throw new FormatException("The session account changed unexpectedly.");
                    CurrentUser = user;
                }
                catch (Exception exception) { failure?.Invoke(InvalidResponse(exception, false)); return; }
                success?.Invoke(user);
            }, failure);
        }

        public IEnumerator FetchCharacter(Action<CharacterDto> success, Action<ApiError> failure)
        {
            yield return Send("GET", baseUrl + "/api/character/", null, true, false, json =>
            {
                CharacterDto character;
                try
                {
                    character = ApiContract.ParseCharacter(json);
                    if (CurrentUser == null || character.username != CurrentUser.username)
                        throw new FormatException("The character does not belong to the signed-in account.");
                }
                catch (Exception exception) { failure?.Invoke(InvalidResponse(exception, false)); return; }
                success?.Invoke(character);
            }, failure);
        }

        /// <summary>Read-only receipt metadata; no journal text, reward mint, or claim request.</summary>
        public IEnumerator FetchMeadow(Action<MeadowDto> success, Action<ApiError> failure)
        {
            yield return Send("GET", baseUrl + "/api/chronicle/meadow/", null, true, false, json =>
            {
                MeadowDto meadow;
                try { meadow = ApiContract.ParseMeadow(json); }
                catch (Exception exception) { failure?.Invoke(InvalidResponse(exception, false)); return; }
                success?.Invoke(meadow);
            }, failure);
        }

        public IEnumerator FetchCoins(Action<CoinBalanceDto> success, Action<ApiError> failure)
        {
            int userId = CurrentUser != null ? CurrentUser.id : 0;
            yield return FetchProjection("/api/coins/", json => ApiContract.ParseCoins(json, userId), success, failure);
        }

        public IEnumerator FetchRecentDrops(Action<DropDto[]> success, Action<ApiError> failure)
        {
            yield return FetchProjection("/api/drops/recent/", ApiContract.ParseRecentDrops, success, failure);
        }

        public IEnumerator FetchUnreadNotificationCount(Action<UnreadCountDto> success, Action<ApiError> failure)
        {
            yield return FetchProjection("/api/notifications/unread_count/", ApiContract.ParseUnreadCount, success, failure);
        }

        public IEnumerator FetchStable(Action<StableDto> success, Action<ApiError> failure)
        {
            yield return FetchProjection("/api/pets/stable/", ApiContract.ParseStable, success, failure);
        }

        private IEnumerator FetchProjection<T>(string path, Func<string, T> parse, Action<T> success, Action<ApiError> failure)
        {
            yield return Send("GET", baseUrl + path, null, true, false, json =>
            {
                T result;
                try { result = parse(json); }
                catch (Exception exception) { failure?.Invoke(InvalidResponse(exception, false)); return; }
                success?.Invoke(result);
            }, failure);
        }

        /// <summary>Fetch one bounded page on demand. Reading never marks an item
        /// read. Only same-origin, forward page-number continuations are accepted.</summary>
        public IEnumerator FetchNotifications(Action<NotificationPageDto> success, Action<ApiError> failure, string pageUrl = null)
        {
            string requested = pageUrl ?? baseUrl + "/api/notifications/";
            if (!TryResolveNotificationPageUrl(baseUrl, requested, out var resolved))
            {
                failure?.Invoke(new ApiError("The notification page link was unsafe or invalid."));
                yield break;
            }
            yield return Send("GET", resolved, null, true, false, json =>
            {
                NotificationPageDto page;
                try
                {
                    page = ApiContract.ParseNotificationPage(json);
                    if (page.next != null)
                    {
                        if (!TryResolveNotificationPageUrl(baseUrl, page.next, out var next) || NotificationPageNumber(next) <= NotificationPageNumber(resolved))
                            throw new FormatException("The notification continuation was unsafe or repeating.");
                        page.next = next;
                    }
                }
                catch (Exception exception) { failure?.Invoke(InvalidResponse(exception, false)); return; }
                foreach (var item in page.results) knownNotifications.Add(item.id);
                success?.Invoke(page);
            }, failure);
        }

        public static bool TryResolveNotificationPageUrl(string origin, string next, out string resolved)
        {
            resolved = null;
            if (!TryValidateBaseUrl(origin, out var validatedOrigin, out _) || string.IsNullOrWhiteSpace(next)
                || next.Length > 2048 || next.IndexOf('\\') >= 0 || !Uri.TryCreate(validatedOrigin + "/", UriKind.Absolute, out var baseUri)
                || !Uri.TryCreate(baseUri, next, out var uri)) return false;
            if (uri.Scheme != baseUri.Scheme || uri.IdnHost != baseUri.IdnHost || uri.Port != baseUri.Port
                || !string.IsNullOrEmpty(uri.UserInfo) || !string.IsNullOrEmpty(uri.Fragment) || uri.AbsolutePath != "/api/notifications/") return false;
            int page = NotificationPageNumber(uri.AbsoluteUri);
            if (page < 1 || page > 500) return false;
            resolved = validatedOrigin + "/api/notifications/" + (page == 1 ? "" : "?page=" + page);
            return true;
        }

        private static int NotificationPageNumber(string url)
        {
            if (!Uri.TryCreate(url, UriKind.Absolute, out var uri)) return 0;
            if (uri.Query.Length == 0) return 1;
            return uri.Query.StartsWith("?page=", StringComparison.Ordinal)
                && int.TryParse(uri.Query.Substring(6), NumberStyles.None, CultureInfo.InvariantCulture, out var page) ? page : 0;
        }

        /// <summary>Explicit, idempotent acknowledgement of a fetched notification.
        /// It never awards anything or consumes other notification/reveal queues.</summary>
        public IEnumerator MarkNotificationRead(int id, Action<NotificationDto> success, Action<ApiError> failure)
        {
            SynchronizeBrowserSession();
            if (!IsAuthenticated)
            {
                failure?.Invoke(new ApiError("Sign in before opening account notifications.", requiresLogin: true));
                yield break;
            }
            if (id < 1 || !knownNotifications.Contains(id))
            {
                failure?.Invoke(new ApiError("Refresh the inbox before opening that notification."));
                yield break;
            }
            yield return Send("POST", baseUrl + "/api/notifications/" + id + "/mark_read/", "{}", true, true, json =>
            {
                NotificationDto receipt;
                try
                {
                    receipt = ApiContract.ParseNotification(json);
                    if (receipt.id != id || !receipt.is_read) throw new FormatException("The server did not confirm this notification as read.");
                }
                catch (Exception exception) { failure?.Invoke(InvalidResponse(exception, false)); return; }
                success?.Invoke(receipt);
            }, failure, idempotentAcknowledgement: true);
        }

        /// <summary>Retrieves all DRF pages, validates each page URL before sending
        /// credentials, and returns only this account's published active habits
        /// supporting positive taps. Daily-limit rows remain visible for feedback.</summary>
        public IEnumerator FetchHabits(Action<HabitDto[]> success, Action<ApiError> failure)
        {
            int version = sessionVersion;
            var habits = new List<HabitDto>();
            var ids = new HashSet<int>();
            var visited = new HashSet<string>(StringComparer.Ordinal);
            string next = baseUrl + "/api/habits/";
            while (!string.IsNullOrEmpty(next))
            {
                if (!TryResolveHabitPageUrl(baseUrl, next, out var pageUrl) || !visited.Add(pageUrl) || visited.Count > 500)
                {
                    failure?.Invoke(new ApiError("The server returned an unsafe or repeating habit pagination link."));
                    yield break;
                }
                HabitPageDto page = null;
                ApiError error = null;
                yield return Send("GET", pageUrl, null, true, false, json =>
                {
                    try { page = ApiContract.ParseHabitPage(json); }
                    catch (Exception exception) { error = InvalidResponse(exception, false); }
                }, problem => error = problem);
                if (error != null) { failure?.Invoke(error); yield break; }
                if (version != sessionVersion || !IsAuthenticated)
                {
                    failure?.Invoke(new ApiError("The session ended before habits could be loaded.", requiresLogin: true));
                    yield break;
                }
                foreach (var habit in page.results)
                {
                    if (!ids.Add(habit.id) || ids.Count > 10000)
                    {
                        failure?.Invoke(new ApiError("The server returned duplicate or too many habit records. Refresh the task board."));
                        yield break;
                    }
                    if (habit.IsEligibleForUser(CurrentUser.id)) habits.Add(habit);
                }
                next = page.next;
            }
            knownHabits.Clear();
            foreach (var habit in habits) knownHabits.Add(habit.id, habit);
            success?.Invoke(habits.ToArray());
        }

        public static bool TryResolveHabitPageUrl(string origin, string next, out string resolved)
        {
            resolved = null;
            if (!Uri.TryCreate(origin + "/", UriKind.Absolute, out var baseUri) ||
                !Uri.TryCreate(baseUri, next, out var uri)) return false;
            if (uri.Scheme != baseUri.Scheme || uri.IdnHost != baseUri.IdnHost || uri.Port != baseUri.Port ||
                !string.IsNullOrEmpty(uri.UserInfo) || !string.IsNullOrEmpty(uri.Fragment) ||
                uri.AbsolutePath != "/api/habits/") return false;
            resolved = uri.AbsoluteUri;
            return true;
        }

        /// <summary>Logs exactly one explicit positive tap. The habit must come
        /// from the most recent successful FetchHabits call. On OutcomeUnknown,
        /// reload state instead of retrying the POST.</summary>
        public IEnumerator LogPositiveHabit(HabitDto habit, Action<HabitTapDto> success, Action<ApiError> failure)
        {
            if (!IsAuthenticated)
            {
                failure?.Invoke(new ApiError("Sign in before logging a real ritual.", requiresLogin: true));
                yield break;
            }
            if (habit == null || !knownHabits.TryGetValue(habit.id, out var known) || !known.IsEligibleForUser(CurrentUser.id))
            {
                failure?.Invoke(new ApiError("Reload the task board before logging that ritual."));
                yield break;
            }
            if (known.DailyLimitReached)
            {
                failure?.Invoke(new ApiError("You have already reached this ritual's daily limit."));
                yield break;
            }
            yield return Send("POST", baseUrl + "/api/habits/" + known.id + "/log/",
                JsonUtility.ToJson(new TapBody()), true, true, json =>
                {
                    HabitTapDto result;
                    try { result = ApiContract.ParseHabitTap(json); }
                    catch (Exception exception)
                    {
                        knownHabits.Clear();
                        failure?.Invoke(InvalidResponse(exception, true));
                        return;
                    }
                    known.strength = result.new_strength;
                    known.taps_today++;
                    habit.strength = known.strength;
                    habit.taps_today = known.taps_today;
                    success?.Invoke(result);
                }, error =>
                {
                    // A refreshed server list is required before another tap if
                    // the prior result was ambiguous; the cache cannot authorize it.
                    if (error.OutcomeUnknown) knownHabits.Clear();
                    failure?.Invoke(error);
                });
        }

        private IEnumerator Send(string method, string url, string json, bool authenticated, bool mutation,
            Action<string> success, Action<ApiError> failure, bool validatingSession = false, bool idempotentAcknowledgement = false)
        {
            SynchronizeBrowserSession();
            bool validOrigin = TryValidateBaseUrl(baseUrl, out _, out var error);
            if (configurationError != null || !validOrigin)
            {
                failure?.Invoke(new ApiError(configurationError ?? error));
                yield break;
            }
            if (authenticated && (string.IsNullOrEmpty(token) || (!validatingSession && !IsAuthenticated)))
            {
                failure?.Invoke(new ApiError("Sign in to connect to your Abby account.", requiresLogin: true));
                yield break;
            }
            if (mutation && MutationInFlight)
            {
                failure?.Invoke(new ApiError("Wait for the current action to finish saving."));
                yield break;
            }
            int version = sessionVersion;
            string requestToken = token;
            if (mutation) MutationInFlight = true;
            string requestUrl = string.Equals(method, "GET", StringComparison.OrdinalIgnoreCase)
                ? BuildReadUrl(url) : url;
            using (var request = new UnityWebRequest(requestUrl, method))
            {
                request.downloadHandler = new DownloadHandlerBuffer();
                request.timeout = Mathf.Clamp(timeoutSeconds, 5, 60);
                // Never forward credentials through a server redirect.
                request.redirectLimit = 0;
                request.SetRequestHeader("Accept", "application/json");
                if (authenticated) request.SetRequestHeader("Authorization", "Token " + requestToken);
                if (json != null)
                {
                    request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
                    request.SetRequestHeader("Content-Type", "application/json");
                }
                activeRequests.Add(request);
                try
                {
                    UnityWebRequestAsyncOperation operation = null;
                    Exception sendException = null;
                    try { operation = request.SendWebRequest(); }
                    catch (Exception exception) { sendException = exception; }
                    if (sendException != null)
                    {
                        failure?.Invoke(new ApiError("The request could not be started. Check the server address and Unity connection settings."));
                        yield break;
                    }
                    yield return operation;
                    SynchronizeBrowserSession();
                    if (version != sessionVersion)
                    {
                        failure?.Invoke(new ApiError(mutation && !idempotentAcknowledgement ?
                            "The session ended while saving. The habit may have been saved; refresh its state before logging again." :
                            "The session ended before the request completed.", outcomeUnknown: mutation && !idempotentAcknowledgement, requiresLogin: true));
                        yield break;
                    }
                    bool transportFailure = request.result == UnityWebRequest.Result.ConnectionError ||
                        request.result == UnityWebRequest.Result.DataProcessingError;
                    if (request.result != UnityWebRequest.Result.Success || request.responseCode < 200 || request.responseCode >= 300)
                    {
                        var problem = ApiContract.HttpError(request.responseCode, request.downloadHandler.text, mutation && !idempotentAcknowledgement, transportFailure);
                        if (problem.RequiresLogin)
                        {
#if UNITY_WEBGL && !UNITY_EDITOR
                            // Only the rejected credential may be discarded. A
                            // late 401 cannot erase a newer journal account.
                            if (authenticated && request.responseCode == 401)
                                AbbySession_ClearToken(requestToken);
#endif
                            ClearSession();
                        }
                        failure?.Invoke(problem);
                        yield break;
                    }
                    success?.Invoke(request.downloadHandler.text);
                }
                finally
                {
                    activeRequests.Remove(request);
                    if (mutation) MutationInFlight = false;
                }
            }
        }

        private static ApiError InvalidResponse(Exception exception, bool mutation)
        {
            string message = exception is FormatException ? exception.Message : "The server returned an unreadable response.";
            if (mutation) message += " The habit may have been saved. Refresh its state before logging it again.";
            return new ApiError(message, outcomeUnknown: mutation);
        }
    }
}
