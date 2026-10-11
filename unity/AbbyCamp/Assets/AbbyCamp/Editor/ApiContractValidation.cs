using System;
using System.Collections.Generic;
using AbbyCamp.Data;
using AbbyCamp.Services;
using UnityEditor;
using UnityEngine;

namespace AbbyCamp.Editor
{
    /// <summary>Focused contract checks, also callable by Unity batch mode with
    /// -executeMethod AbbyCamp.Editor.ApiContractValidation.Run.</summary>
    public static class ApiContractValidation
    {
        private const string Habit = "{\"id\":9,\"name\":\"Read {a} book \\\"today\\\"\",\"habit_type\":\"positive\",\"user\":7,\"xp_reward\":5,\"max_taps_per_day\":1,\"taps_today\":0,\"strength\":-2,\"is_active\":true,\"pending_parent_review\":false,\"skill_tags\":[{\"skill\":2,\"skill_name\":\"Reading\",\"xp_weight\":1}]}";
        private static int checks;

        [MenuItem("Abby Camp/Validate API Contracts")]
        public static void Run()
        {
            checks = 0;
            var user = ApiContract.ParseLogin("{\"id\":7,\"username\":\"abby\",\"display_name\":\"Abby\",\"role\":\"child\",\"token\":\"0123456789012345678901234567890123456789\"}", out var token);
            Check(user.id == 7 && user.DisplayName == "Abby" && token.Length == 40, "Flat Django login response");
            Reject(() => ApiContract.ParseLogin("{\"id\":7,\"username\":\"abby\",\"role\":\"child\",\"token\":\"bad\"}", out _), "Missing/invalid token");
            Reject(() => ApiContract.ParseUser("{\"username\":\"abby\",\"role\":\"child\"}"), "Missing identity");
            Reject(() => ApiContract.ParseUser("{\"id\":7,\"username\":\"abby\",\"role\":\"staff\"}"), "Unknown account role");
            var page = ApiContract.ParseHabitPage("{\"count\":21,\"next\":\"http://localhost:8000/api/habits/?page=2\",\"previous\":null,\"results\":[" + Habit + "]}");
            Check(page.count == 21 && page.results.Length == 1 && page.results[0].name == "Read {a} book \"today\"", "Paginated habits and escaped strings");
            var habit = page.results[0];
            Check(habit.IsEligibleForUser(7) && !habit.IsEligibleForUser(8), "Only own habits");
            habit.is_active = false;
            Check(!habit.IsEligibleForUser(7), "Inactive habits excluded");
            habit.is_active = true;
            habit.pending_parent_review = true;
            Check(!habit.IsEligibleForUser(7), "Unapproved habits excluded");
            habit.pending_parent_review = false;
            habit.habit_type = "negative";
            Check(!habit.IsEligibleForUser(7), "Negative-only habits excluded");
            habit.habit_type = "both";
            Check(habit.IsEligibleForUser(7), "Both-direction habits allow positive taps");
            habit.taps_today = habit.max_taps_per_day;
            Check(habit.DailyLimitReached, "Daily tap cap");
            Reject(() => ApiContract.ParseHabit(Habit.Replace(",\"pending_parent_review\":false", "")), "Missing approval cannot silently allow tapping");
            Reject(() => ApiContract.ParseHabit(Habit.Replace("\"is_active\":true", "\"is_active\":\"true\"")), "Safety flags must be booleans");
            Reject(() => ApiContract.ParseHabitPage("{\"count\":0,\"next\":null}"), "Missing results cannot masquerade as empty list");
            var empty = ApiContract.ParseHabitPage("{\"count\":0,\"next\":null,\"results\":[]}");
            Check(empty.results.Length == 0 && empty.next == null, "Empty final habit page");
            var tap = ApiContract.ParseHabitTap("{\"direction\":1,\"xp_reward\":5,\"new_strength\":0,\"game_event\":null}");
            Check(tap.direction == 1 && tap.new_strength == 0 && tap.game_event == null, "Confirmed tap remains valid without optional game event");
            var partialTap = ApiContract.ParseHabitTap("{\"direction\":1,\"xp_reward\":0,\"new_strength\":1,\"game_event\":{\"streak\":null,\"quest\":null,\"daily_challenge\":null,\"drops\":[],\"notifications\":[]}}");
            Check(partialTap.game_event != null && partialTap.game_event.streak == null && partialTap.game_event.quest == null && partialTap.game_event.daily_challenge == null, "Optional event nulls retain absent-event semantics");
            Reject(() => ApiContract.ParseHabitTap("{\"error\":\"No reward\",\"game_event\":{\"direction\":1,\"xp_reward\":5,\"new_strength\":2}}"), "Nested keys cannot fake a confirmed tap");
            Reject(() => ApiContract.ParseHabitTap("{\"direction\":-1,\"xp_reward\":0,\"new_strength\":2}"), "Positive-tap confirmation required");
            Reject(() => ApiContract.ParseHabitTap("{\"direction\":1,\"direction\":-1,\"xp_reward\":0,\"new_strength\":2}"), "Duplicate response keys rejected");
            Reject(() => ApiContract.ParseHabitTap("{\"direction\":1,\"xp_reward\":0,\"new_strength\":2}" + " trailing"), "Trailing response data rejected");
            var eventTap = ApiContract.ParseHabitTap("{\"direction\":1,\"xp_reward\":5,\"new_strength\":3,\"game_event\":{\"streak\":{\"is_first_today\":true,\"check_in_bonus_coins\":5,\"streak\":2},\"drops\":[{\"item_id\":4,\"item_name\":\"Fox egg\",\"quantity\":1,\"was_salvaged\":false}],\"quest\":{\"quest_name\":\"Forest trial\",\"completed\":true},\"daily_challenge\":{\"newly_completed\":true}}}");
            string withoutSkill = eventTap.DescribeConfirmedOutcome(new HabitDto());
            Check(withoutSkill == "Ritual recorded. Strength: 3." && eventTap.game_event.drops[0].item_name == "Fox egg", "Confirmation omits unverified event rewards while retaining event data");
            Check(eventTap.DescribeConfirmedOutcome(ApiContract.ParseHabit(Habit)) == "Ritual recorded. Strength: 3." && tap.DescribeConfirmedOutcome() == "Ritual recorded. Strength: 0.", "Configured XP and null game event do not change confirmed base outcome");
            var definite = ApiContract.HttpError(400, "{\"error\":\"Daily limit reached\"}", true, false);
            Check(!definite.OutcomeUnknown && definite.Message == "Daily limit reached", "Validation rejection is definite");
            Check(ApiContract.HttpError(503, "<html>down</html>", true, false).OutcomeUnknown, "Server error after POST may have committed");
            Check(ApiContract.HttpError(408, "", true, false).OutcomeUnknown, "HTTP timeout after POST may have committed");
            Check(ApiContract.HttpError(0, "", true, true).OutcomeUnknown, "Lost POST response may have committed");
            Check(!ApiContract.HttpError(0, "", false, true).OutcomeUnknown, "Failed reads are not failed mutations");
            Check(ApiContract.HttpError(401, "{\"detail\":\"Invalid token.\"}", false, false).RequiresLogin, "Expired token ends session");
            Check(AbbyApiClient.TryValidateBaseUrl("http://127.0.0.1:8000/", out var origin, out _) && origin == "http://127.0.0.1:8000", "Loopback HTTP origin normalized");
            Check(AbbyApiClient.TryValidateBaseUrl("http://localhost:8000", out _, out _), "Localhost HTTP allowed");
            Check(AbbyApiClient.TryValidateBaseUrl("https://abby.example.com", out _, out _), "Remote HTTPS allowed");
            Check(!AbbyApiClient.TryValidateBaseUrl("http://192.168.1.2:8000", out _, out _), "Remote HTTP prohibited");
            Check(!AbbyApiClient.TryValidateBaseUrl("https://abby.example.com/api/", out _, out _), "Origin must not include an endpoint path");
            Check(!AbbyApiClient.TryValidateBaseUrl("https://user:pass@abby.example.com", out _, out _), "Embedded credentials rejected");
            Check(AbbyApiClient.TryResolveHabitPageUrl("https://abby.example.com", "/api/habits/?page=2", out _), "Same-origin pagination supported");
            Check(!AbbyApiClient.TryResolveHabitPageUrl("https://abby.example.com", "https://other.example.com/api/habits/?page=2", out _), "Pagination cannot exfiltrate token to another host");
            Check(!AbbyApiClient.TryResolveHabitPageUrl("https://abby.example.com", "http://abby.example.com/api/habits/?page=2", out _), "Pagination cannot downgrade HTTPS");
            Check(!AbbyApiClient.TryResolveHabitPageUrl("https://abby.example.com", "/api/auth/", out _), "Pagination restricted to habit endpoint");

            const string bloom = "{\"receipt_id\":\"journal:123\",\"type\":\"memory_bloom\",\"title\":\"Memory bloom\",\"earned_at\":\"2026-10-10T12:34:56Z\"}";
            const string meadowJson = "{\"schema_version\":1,\"keepsake_count\":1,\"journal_xp_awarded\":5,\"keepsakes\":[" + bloom + "]}";
            var meadow = ApiContract.ParseMeadow(meadowJson);
            Check(meadow.keepsake_count == 1 && meadow.keepsakes[0].receipt_id == "journal:123", "Read-only meadow receipt metadata");
            var emptyMeadow = ApiContract.ParseMeadow("{\"schema_version\":1,\"keepsake_count\":0,\"journal_xp_awarded\":0,\"keepsakes\":[]}");
            Check(emptyMeadow.keepsakes.Length == 0, "Empty collection remains a valid acknowledged read");
            Reject(() => ApiContract.ParseMeadow(meadowJson.Replace("\"schema_version\":1", "\"schema_version\":2")), "Unknown meadow schema cannot be displayed as progress");
            Reject(() => ApiContract.ParseMeadow(meadowJson.Replace("\"keepsake_count\":1", "\"keepsake_count\":0")), "Collection count cannot be smaller than its window");
            Reject(() => ApiContract.ParseMeadow(meadowJson.Replace("journal:123", "journal:invalid")), "Keepsake requires stable journal receipt identity");
            Reject(() => ApiContract.ParseMeadow(meadowJson.Replace("memory_bloom", "unverified_reward")), "Unknown reward type is not recognised as an earned bloom");
            Reject(() => ApiContract.ParseMeadow(meadowJson.Replace("2026-10-10T12:34:56Z", "not-a-date")), "Keepsake requires an earned date");
            Reject(() => ApiContract.ParseMeadow("{\"schema_version\":1,\"keepsake_count\":2,\"journal_xp_awarded\":10,\"keepsakes\":[" + bloom + "," + bloom + "]}"), "Duplicate keepsake receipts rejected");
            var localMemory = new Dictionary<string, string>();
            string Read(string key) => localMemory.TryGetValue(key, out var value) ? value : "";
            void Remember(string key, string value) => localMemory[key] = value;
            Check(MeadowReceiptMemory.Observe("https://abby.example.com", 7, meadow, Read, Remember) == null, "First visit baselines existing awarded history without replaying a celebration");
            var nextMeadow = ApiContract.ParseMeadow(meadowJson.Replace("journal:123", "journal:124").Replace("12:34:56Z", "12:35:56Z"));
            Check(MeadowReceiptMemory.Observe("https://abby.example.com", 7, nextMeadow, Read, Remember)?.receipt_id == "journal:124", "New acknowledged receipt celebrates locally");
            Check(MeadowReceiptMemory.Observe("https://abby.example.com", 7, nextMeadow, Read, Remember) == null, "Refresh cannot replay receipt celebration");
            Check(MeadowReceiptMemory.Observe("https://abby.example.com", 7, emptyMeadow, Read, Remember) == null
                && MeadowReceiptMemory.Observe("https://abby.example.com", 7, meadow, Read, Remember) == null, "Deletion and older window items cannot replay historical celebrations");
            Check(MeadowReceiptMemory.Observe("https://abby.example.com", 8, nextMeadow, Read, Remember) == null, "Receipt presentation baselines separately for another child");
            Check(MeadowReceiptMemory.Observe("https://other.example.com", 7, nextMeadow, Read, Remember) == null, "Receipt presentation stays scoped to its server origin");

            ValidatePlayHomeContracts();
            var gameObject = new GameObject("API validation client");
            try
            {
                var client = gameObject.AddComponent<AbbyApiClient>();
                ApiError rejection = null;
                bool completed = false;
                var coroutine = client.LogPositiveHabit(null, _ => completed = true, problem => rejection = problem);
                Check(!coroutine.MoveNext() && !completed && rejection != null && rejection.RequiresLogin, "Logged-out tap never issues a request");
                rejection = null;
                coroutine = client.ResumeBrowserSession(_ => completed = true, problem => rejection = problem);
                Check(!coroutine.MoveNext() && !completed && rejection != null && rejection.RequiresLogin && !client.IsAuthenticated,
                    "Missing browser credential cannot mint a token or authorize camp actions");
                rejection = null;
                coroutine = client.MarkNotificationRead(1, _ => completed = true, problem => rejection = problem);
                Check(!coroutine.MoveNext() && !completed && rejection != null && rejection.RequiresLogin,
                    "Logged-out notification acknowledgement never issues a request");
                rejection = null;
                coroutine = client.FetchNotifications(_ => completed = true, problem => rejection = problem, "https://outside.example.com/api/notifications/?page=2");
                Check(!coroutine.MoveNext() && !completed && rejection != null,
                    "Unsafe inbox continuation is rejected before a request starts");
                client.ConfigureBaseUrl("https://abby.example.com", out _);
                Check(!client.ConfigureBaseUrl("http://remote.example.com", out _) && client.BaseUrl == "https://abby.example.com", "Rejected configuration preserves valid origin");
            }
            finally { UnityEngine.Object.DestroyImmediate(gameObject); }
            Debug.Log("Abby Camp API contracts: " + checks + " checks passed.");
        }

        private static void ValidatePlayHomeContracts()
        {
            const string date = "2026-10-10T12:34:56Z";
            const string transaction = "{\"id\":12,\"user\":7,\"amount\":-5,\"reason\":\"redemption\",\"description\":\"Reward shelf\",\"created_at\":\"" + date + "\"}";
            const string coinsJson = "{\"balance\":120,\"breakdown\":{\"redemption\":-5},\"recent_transactions\":[" + transaction + "]}";
            var coins = ApiContract.ParseCoins(coinsJson, 7);
            Check(coins.balance == 120 && coins.recent_transactions[0].amount == -5, "Authoritative coin history retains signed spending amounts");
            Check(ApiContract.ParseCoins("{\"balance\":0,\"recent_transactions\":[]}", 7).recent_transactions.Length == 0, "An empty coin ledger is valid");
            Reject(() => ApiContract.ParseCoins(coinsJson, 8), "Another account's coin ledger is rejected");
            Reject(() => ApiContract.ParseCoins(coinsJson.Replace("\"amount\":-5,", ""), 7), "Missing transaction amounts cannot default into rewards");
            Reject(() => ApiContract.ParseCoins("{\"balance\":120,\"recent_transactions\":[" + transaction + "," + transaction + "]}", 7), "Duplicate ledger records are rejected");
            const string drop = "{\"id\":4,\"item\":3,\"item_name\":\"Fox egg\",\"item_icon\":\"egg\",\"item_sprite_key\":\"fox-egg\",\"item_rarity\":\"rare\",\"trigger_type\":\"homework_approved\",\"quantity\":2,\"was_salvaged\":true,\"created_at\":\"" + date + "\"}";
            var drops = ApiContract.ParseRecentDrops("[" + drop + "]");
            Check(drops[0].id == 4 && drops[0].quantity == 2 && drops[0].was_salvaged, "Committed drops retain identity, quantity and salvage state");
            Check(ApiContract.ParseRecentDrops("[]").Length == 0, "No drops is a valid history");
            Reject(() => ApiContract.ParseRecentDrops("[" + drop + "," + drop + "]"), "Duplicate drop IDs cannot be announced twice");
            Reject(() => ApiContract.ParseRecentDrops("[" + drop.Replace("\"was_salvaged\":true", "\"was_salvaged\":\"true\"") + "]"), "Salvage state requires an explicit boolean");
            Reject(() => ApiContract.ParseRecentDrops("[" + drop.Replace("\"quantity\":2", "\"quantity\":0") + "]"), "Drop quantities must be positive");
            Reject(() => ApiContract.ParseRecentDrops("[" + new string(' ', 2 * 1024 * 1024) + "]"), "Oversized bare-array responses are bounded");

            const string notification = "{\"id\":20,\"title\":\"New drop\",\"message\":\"An egg is waiting\",\"notification_type\":\"drop_received\",\"is_read\":false,\"created_at\":\"" + date + "\",\"link\":\"/inventory\"}";
            var page = ApiContract.ParseNotificationPage("{\"count\":21,\"next\":\"https://abby.example.com/api/notifications/?page=2\",\"results\":[" + notification + "]}");
            Check(page.count == 21 && !page.results[0].is_read && page.next.EndsWith("page=2"), "Inbox parsing preserves unread state and pagination");
            Check(ApiContract.ParseNotificationPage("{\"count\":0,\"next\":null,\"results\":[]}").next == null, "An empty inbox uses a true null continuation");
            Check(ApiContract.ParseUnreadCount("{\"count\":35}").count == 35, "Global unread count is independent of the latest page");
            Reject(() => ApiContract.ParseNotification(notification.Replace(",\"is_read\":false", "")), "Missing read state cannot silently acknowledge a notification");
            Reject(() => ApiContract.ParseNotification(notification.Replace(date, "invalid")), "Notification dates are validated");
            Reject(() => ApiContract.ParseUnreadCount("{\"count\":-1}"), "Unread counts cannot be negative");
            Reject(() => ApiContract.ParseNotificationPage("{\"count\":2,\"next\":null,\"results\":[" + notification + "," + notification + "]}"), "Duplicate inbox rows are rejected");
            Reject(() => ApiContract.ParseNotificationPage("{\"count\":0,\"next\":\"?page=2\",\"results\":[]}"), "An empty page cannot authorize a continuation loop");
            Check(AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?page=2", out var next) && next == "https://abby.example.com/api/notifications/?page=2", "Inbox page URLs stay at the same-origin endpoint");
            foreach (string unsafePage in new[] { "https://other.example.com/api/notifications/?page=2", "http://abby.example.com/api/notifications/?page=2", "/api/auth/", "/api/notifications/?page=0", "/api/notifications/?page=501", "/api/notifications/?page=2&token=x", "/api/notifications/?page=2#secret", "https://user@abby.example.com/api/notifications/?page=2" })
                Check(!AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", unsafePage, out _), "Unsafe inbox page rejected: " + unsafePage);

            const string species = "{\"id\":1,\"name\":\"Fox\",\"icon\":\"fox\",\"sprite_key\":\"fox\",\"description\":\"Friendly\",\"food_preference\":\"fruit\"}";
            const string potion = "{\"id\":2,\"slug\":null,\"name\":\"Mint\",\"sprite_key\":\"mint\",\"color_hex\":\"#AABBCC\",\"rarity\":\"common\",\"description\":\"Soft green\"}";
            const string pet = "{\"id\":8,\"species\":" + species + ",\"potion\":" + potion + ",\"name\":\"Clover\",\"growth_points\":12,\"is_active\":true,\"evolved_to_mount\":false,\"is_fully_grown\":false,\"happiness_level\":\"happy\",\"last_fed_at\":null,\"created_at\":\"" + date + "\",\"updated_at\":\"" + date + "\"}";
            const string mount = "{\"id\":5,\"species\":" + species + ",\"potion\":" + potion + ",\"is_active\":true,\"last_bred_at\":null,\"active_expedition\":null,\"created_at\":\"" + date + "\",\"updated_at\":\"" + date + "\"}";
            const string stableJson = "{\"pets\":[" + pet + "],\"mounts\":[" + mount + "],\"total_pets\":1,\"total_mounts\":1,\"total_possible\":2}";
            var stable = ApiContract.ParseStable(stableJson);
            Check(stable.ActiveCompanion?.DisplayName == "Clover" && stable.ActiveMount?.DisplayName == "Mint Fox", "Stable reflects genuinely owned active creatures");
            Check(stable.pets[0].last_fed_at == null && stable.mounts[0].last_bred_at == null, "Nullable care dates do not become fabricated timestamps");
            Check(ApiContract.ParseStable("{\"pets\":[],\"mounts\":[],\"total_pets\":0,\"total_mounts\":0,\"total_possible\":0}").ActiveCompanion == null, "Empty ownership does not invent a starter companion");
            Check(ApiContract.ParseStable(stableJson.Replace("\"evolved_to_mount\":false", "\"evolved_to_mount\":true")).ActiveCompanion == null, "Evolved pets do not masquerade as the active companion");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"total_pets\":1", "\"total_pets\":0")), "Stable ownership counts must agree with its arrays");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"growth_points\":12", "\"growth_points\":101")), "Out-of-range companion growth is rejected");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"is_fully_grown\":false", "\"is_fully_grown\":true")), "Growth status cannot be fabricated by missing or inconsistent state");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"color_hex\":\"#AABBCC\"", "\"color_hex\":\"invalid\"")), "Potion colors cannot be untrusted markup");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"species\":" + species, "\"species\":null")), "Owned creature species are required");

            Check(AbbyApiClient.DestinationPath((PlayDestination)999) == null, "Unknown typed destinations cannot navigate");
            Check(AbbyApiClient.TryResolveNotificationDestination("/inventory", "drop_received", out var destination) && destination == PlayDestination.Satchel, "Legacy inventory links resolve to Satchel");
            Check(AbbyApiClient.TryResolveNotificationDestination("/projects/123", "project_approved", out destination) && destination == PlayDestination.TasksVentures, "Legacy project detail links resolve to its task tab");
            Check(AbbyApiClient.TryResolveNotificationDestination("/chronicle?tab=grades", "journal_reply", out destination) && destination == PlayDestination.Grades, "Safe notification link retains the appropriate memoir tab");
            Check(AbbyApiClient.TryResolveNotificationDestination("/unknown", "print_finished", out destination) && destination == PlayDestination.TasksForge, "Known notification types supply a typed fallback");
            Check(AbbyApiClient.TryResolveNotificationDestination("https://outside.example.com/", "journal_reply", out destination) && destination == PlayDestination.Journal, "Unsafe links can only fall back to a known typed destination");
            foreach (string unsafeLink in new[] { "https://outside.example.com/", "//outside.example.com/", "/\\outside.example.com/", "/chronicle?tab=journal&token=secret", "/%2foutside.example.com/", "/bestiary#secret", "/unknown" })
                Check(!AbbyApiClient.TryResolveNotificationDestination(unsafeLink, "unknown_type", out _), "Raw or unknown notification destinations are never followed: " + unsafeLink);
        }

        private static void Check(bool condition, string description)
        {
            checks++;
            if (!condition) throw new InvalidOperationException("API contract validation failed: " + description);
        }

        private static void Reject(Action parse, string description)
        {
            bool rejected = false;
            try { parse(); }
            catch (FormatException) { rejected = true; }
            catch (ArgumentException) { rejected = true; }
            Check(rejected, description);
        }
    }
}
