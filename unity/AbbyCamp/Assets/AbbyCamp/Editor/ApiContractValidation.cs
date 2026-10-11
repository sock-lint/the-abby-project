using System;
using System.IO;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
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
            ValidateSharedResponses();
            ValidateGreenlightFixtures();
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
            ValidateCompanionCareContracts();
            ValidateHatchingContracts();
            var gameObject = new GameObject("API validation client");
            try
            {
                var client = gameObject.AddComponent<AbbyApiClient>();
                string readUrl = client.BuildReadUrl("https://abby.example.com/api/auth/me/");
                string readNamespace = new Uri(readUrl).Query.Substring("?_abby_session=".Length);
                Check(Guid.TryParseExact(readNamespace, "N", out _), "Private reads use a random noncredential namespace");
                Check(client.BuildReadUrl("https://abby.example.com/api/character/").EndsWith("?_abby_session=" + readNamespace),
                    "Private reads share one namespace within a session");
                string pageUrl = client.BuildReadUrl("https://abby.example.com/api/habits/?page=2&name=a%26b&_abby_session=old&%5Fabby_session=older&_abby_session");
                Check(new Uri(pageUrl).Query == "?page=2&name=a%26b&_abby_session=" + readNamespace,
                    "Pagination preserves filters and replaces all inherited session keys");
                client.ClearSession();
                string nextSessionUrl = client.BuildReadUrl("https://abby.example.com/api/auth/me/");
                Check(nextSessionUrl != readUrl && Guid.TryParseExact(new Uri(nextSessionUrl).Query.Substring("?_abby_session=".Length), "N", out _),
                    "Logout or account replacement rotates the read namespace");
                var otherClient = gameObject.AddComponent<AbbyApiClient>();
                Check(otherClient.BuildReadUrl("https://abby.example.com/api/auth/me/") != nextSessionUrl,
                    "New clients cannot reuse a previous page's private read cache");
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
                foreach (var action in new Func<Action<ApiError>, System.Collections.IEnumerator>[]
                {
                    fail => client.FeedPet(51, 71, _ => completed = true, fail),
                    fail => client.ActivatePet(52, _ => completed = true, fail),
                    fail => client.ActivateMount(62, _ => completed = true, fail),
                    fail => client.HatchPet(73, 75, _ => completed = true, fail),
                })
                {
                    rejection = null;
                    coroutine = action(problem => rejection = problem);
                    Check(!coroutine.MoveNext() && !completed && rejection != null && rejection.RequiresLogin,
                        "Logged-out creature care never issues a mutation");
                }
                client.ConfigureBaseUrl("https://abby.example.com", out _);
                Check(!client.ConfigureBaseUrl("http://remote.example.com", out _) && client.BaseUrl == "https://abby.example.com", "Rejected configuration preserves valid origin");
            }
            finally { UnityEngine.Object.DestroyImmediate(gameObject); }
            Debug.Log("Abby Camp API contracts: " + checks + " checks passed.");
        }

        private static void ValidateSharedResponses()
        {
            // These are the same raw Django response bodies used by the backend
            // drift checks and React API tests. Keep them outside Assets so the
            // synthetic account/token data cannot ship in a player build.
            var login = ApiContract.ParseLogin(ReadFixture("auth-login-child.json"), out var token);
            Check(login.id == 7 && login.username == "fixture-child" && login.role == "child"
                && login.DisplayName == "Fixture Child" && token == "0123456789012345678901234567890123456789",
                "Shared Django login response preserves account identity and synthetic token");
            Check(login.family != null && login.family.id == 1 && login.family.timezone == "America/Phoenix",
                "Shared Django login includes the account's family");

            var user = ApiContract.ParseUser(ReadFixture("auth-me-child.json"));
            Check(user.id == login.id && user.username == login.username && user.role == login.role
                && user.family != null && user.family.id == login.family.id,
                "Shared browser session response matches the authenticated account");

            var page = ApiContract.ParseHabitPage(ReadFixture("habits-page-1.json"));
            Check(page.count == 21 && page.results.Length == 20
                && page.next == "http://testserver/api/habits/?page=2",
                "Shared Django habits response retains real pagination");
            var habit = page.results[0];
            Check(habit.id == 9 && habit.name == "Read {a} book \"today\"" && habit.strength == -2
                && habit.taps_today == 0 && habit.IsEligibleForUser(user.id) && !habit.IsEligibleForUser(user.id + 1),
                "Shared habit preserves escaped text, strength, and account eligibility");
            Check(habit.skill_tags.Length == 1 && habit.skill_tags[0].skill == 2
                && habit.skill_tags[0].skill_name == "Reading" && habit.skill_tags[0].xp_weight == 1,
                "Shared habit skill tags survive Unity DTO parsing");
            Check(!page.results[1].IsEligibleForUser(user.id) && page.results[2].IsEligibleForUser(user.id)
                && !page.results[3].IsEligibleForUser(user.id),
                "Shared negative, both-direction, and inactive habits preserve eligibility");

            var lastPage = ApiContract.ParseHabitPage(ReadFixture("habits-page-2.json"));
            Check(lastPage.count == page.count && lastPage.results.Length == 1
                && lastPage.results[0].id == 29 && lastPage.next == null,
                "Shared final habit page preserves the explicit null continuation");
            var emptyPage = ApiContract.ParseHabitPage(ReadFixture("habits-empty.json"));
            Check(emptyPage.count == 0 && emptyPage.results.Length == 0 && emptyPage.next == null,
                "Shared empty habit response remains an empty final page");

            var tap = ApiContract.ParseHabitTap(ReadFixture("habit-positive-tap.json"));
            Check(tap.direction == 1 && tap.xp_reward == 5 && tap.new_strength == -1
                && tap.DescribeConfirmedOutcome(habit) == "Ritual recorded. Strength: -1.",
                "Shared committed tap confirms strength without inventing granted rewards");
            Check(tap.game_event != null && tap.game_event.trigger_type == "habit_log"
                && tap.game_event.streak != null && tap.game_event.streak.streak == 1
                && tap.game_event.drops.Length == 0 && tap.game_event.quest == null
                && tap.game_event.daily_challenge != null && tap.game_event.daily_challenge.progress == 1,
                "Shared real game-loop response preserves nested events and null quest");

            var noEvent = ApiContract.ParseHabitTap(ReadFixture("habit-positive-tap-no-event.json"));
            Check(noEvent.direction == 1 && noEvent.new_strength == -1 && noEvent.game_event == null
                && noEvent.DescribeConfirmedOutcome(habit) == "Ritual recorded. Strength: -1.",
                "Shared committed tap remains confirmed without an optional game event");
            var limit = ApiContract.HttpError(400, ReadFixture("habit-positive-tap-limit.json"), true, false);
            Check(limit.StatusCode == 400 && !limit.OutcomeUnknown
                && limit.Message == "Daily limit reached (1 taps/day).",
                "Shared Django daily-limit response is a definite rejection");
        }

        private static string ReadFixture(string name)
        {
            var path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "contracts", "api", "fixtures", name));
            if (!File.Exists(path))
                throw new FileNotFoundException("Shared API fixture missing. Validate Unity from a full repository checkout: " + name, path);
            return File.ReadAllText(path);
        }

        // Payment actions remain in the parent web app. These Editor-only
        // projections validate the shared response contract without adding a
        // second payout client or shipping synthetic banking data in a player.
        [Serializable] private sealed class GreenlightSnapshotFixture
        {
            public int id;
            public int user;
            public string amount;
            public string as_of;
            public int created_by;
        }

        [Serializable] private sealed class GreenlightPayoutFixture
        {
            public int id;
            public string amount;
            public string transferred_on;
            public string source;
            public bool reconciled;
        }

        [Serializable] private sealed class GreenlightOverviewFixture
        {
            public int user_id;
            public string owed_balance;
            public string approved_payable;
            public string pending_hourly;
            public GreenlightSnapshotFixture balance_snapshot;
            public GreenlightPayoutFixture[] payouts;
        }

        [Serializable] private sealed class GreenlightPayoutResponseFixture
        {
            public bool created;
            public GreenlightPayoutFixture payout;
        }

        [Serializable] private sealed class GreenlightPreviewRowFixture
        {
            public string fingerprint;
            public string amount;
            public bool eligible;
            public int[] match_candidates;
        }

        [Serializable] private sealed class GreenlightPreviewFixture
        {
            public GreenlightPreviewRowFixture[] rows;
            public string[] schema;
        }

        [Serializable] private sealed class GreenlightReconcileFixture
        {
            public int recorded;
            public int matched;
            public int duplicates;
        }

        private static void ValidateGreenlightFixtures()
        {
            string missingJson = ReadFixture("greenlight-overview-no-snapshot.json");
            var missing = JsonUtility.FromJson<GreenlightOverviewFixture>(missingJson);
            Check(missing.user_id == 7 && missing.owed_balance == "25.00"
                && missing.approved_payable == "20.00" && missing.pending_hourly == "5.00",
                "Shared payout overview separates approved money from pending hourly earnings");
            Check(Regex.IsMatch(missingJson, "\"balance_snapshot\"\\s*:\\s*null") && missing.payouts.Length == 0,
                "An unknown Greenlight balance is explicit null, not a fabricated zero");
            foreach (string field in new[] { "owed_balance", "approved_payable", "pending_hourly" })
                Check(HasQuotedMoney(missingJson, field), "Shared payout amount retains exact decimal-string cents: " + field);

            string snapshotJson = ReadFixture("greenlight-balance-snapshot.json");
            var snapshot = JsonUtility.FromJson<GreenlightSnapshotFixture>(snapshotJson);
            Check(snapshot.user == 7 && snapshot.created_by == 6 && snapshot.amount == "40.25"
                && HasQuotedMoney(snapshotJson, "amount")
                && DateTimeOffset.TryParse(snapshot.as_of, CultureInfo.InvariantCulture, DateTimeStyles.None, out var asOf)
                && asOf.ToUniversalTime() == new DateTimeOffset(2026, 10, 11, 18, 0, 0, TimeSpan.Zero),
                "Reported Greenlight balance retains a parent, exact amount and actual as-of timestamp");
            var known = JsonUtility.FromJson<GreenlightOverviewFixture>(ReadFixture("greenlight-overview.json"));
            Check(known.balance_snapshot != null && known.balance_snapshot.id == snapshot.id
                && known.balance_snapshot.amount == snapshot.amount && known.owed_balance == missing.owed_balance,
                "Recording Greenlight's reported balance does not change what the parent owes");

            string payoutJson = ReadFixture("greenlight-payout.json");
            var payout = JsonUtility.FromJson<GreenlightPayoutResponseFixture>(payoutJson);
            Check(payout.created && payout.payout.amount == "12.50" && HasQuotedMoney(payoutJson, "amount")
                && payout.payout.source == "manual" && !payout.payout.reconciled
                && payout.payout.transferred_on == "2026-10-11",
                "Parent-confirmed payout retains amount, transfer date and unreconciled manual source");
            var preview = JsonUtility.FromJson<GreenlightPreviewFixture>(ReadFixture("greenlight-preview.json"));
            Check(preview.schema.Length == 5 && preview.rows.Length == 3 && preview.rows[0].eligible
                && preview.rows[0].match_candidates.Length == 1 && preview.rows[0].match_candidates[0] == payout.payout.id
                && preview.rows[1].eligible && preview.rows[1].amount == "7.50"
                && !preview.rows[2].eligible && preview.rows[2].amount == "-3.00",
                "Statement preview can match a paid transfer without treating card spending as money owed");
            Check(preview.rows[0].fingerprint.Length == 64 && preview.rows[1].fingerprint.Length == 64
                && preview.rows[0].fingerprint != preview.rows[1].fingerprint,
                "Statement transfers preserve stable distinct reconciliation identities");
            var reconciled = JsonUtility.FromJson<GreenlightReconcileFixture>(ReadFixture("greenlight-reconcile.json"));
            Check(reconciled.recorded == 1 && reconciled.matched == 1 && reconciled.duplicates == 0,
                "Reconciliation records one new payout and matches the existing payout once");
            var final = JsonUtility.FromJson<GreenlightOverviewFixture>(ReadFixture("greenlight-overview-reconciled.json"));
            Check(final.owed_balance == "5.00" && final.approved_payable == "0.00" && final.pending_hourly == "5.00"
                && final.balance_snapshot.amount == snapshot.amount && final.balance_snapshot.as_of == snapshot.as_of
                && final.payouts.Length == 2 && final.payouts[0].reconciled && final.payouts[1].reconciled,
                "Confirmed payouts reduce money owed while the separately reported Greenlight balance stays as-of its observation");
        }

        private static bool HasQuotedMoney(string json, string field)
        {
            return Regex.IsMatch(json, "\"" + Regex.Escape(field) + "\"\\s*:\\s*\"-?[0-9]+\\.[0-9]{2}\"");
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
            const string readNamespace = "0123456789abcdef0123456789abcdef";
            Check(AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?_abby_session=" + readNamespace + "&page=2", out next)
                && next == "https://abby.example.com/api/notifications/?page=2",
                "Django inbox continuation strips the inherited private read namespace");
            Check(AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?page=2&_abby_session=" + readNamespace, out next)
                && next == "https://abby.example.com/api/notifications/?page=2",
                "Inbox continuation accepts the namespace after its page number");
            Check(AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?_abby_session=" + readNamespace, out next)
                && next == "https://abby.example.com/api/notifications/",
                "Namespace-only inbox reads resolve to the first page");
            Check(AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?page=2&%5Fabby_session=" + readNamespace, out next)
                && next == "https://abby.example.com/api/notifications/?page=2",
                "URI-normalized private namespace keys are still stripped from inbox continuations");
            Check(AbbyApiClient.TryResolveHabitPageUrl("https://abby.example.com", "/api/habits/?_abby_session=" + readNamespace + "&page=2", out var habitNext)
                && habitNext == "https://abby.example.com/api/habits/?_abby_session=" + readNamespace + "&page=2",
                "Habit continuation retains the inherited namespace for replacement by Send");
            foreach (string unsafeQuery in new[] { "page=2&_abby_session=invalid", "page=2&_abby_session=" + readNamespace + "&token=x", "page=2&page=3&_abby_session=" + readNamespace,
                "page=2&_abby_session=" + readNamespace + "&_abby_session=" + readNamespace, "page=2&%5Fabby_session_extra=" + readNamespace })
                Check(!AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?" + unsafeQuery, out _),
                    "Private namespaces cannot weaken inbox query validation: " + unsafeQuery);
            foreach (string unsafePage in new[] { "https://other.example.com/api/notifications/?page=2", "http://abby.example.com/api/notifications/?page=2", "/api/auth/", "/api/notifications/?page=0", "/api/notifications/?page=501", "/api/notifications/?page=2&token=x", "/api/notifications/?page=2#secret", "https://user@abby.example.com/api/notifications/?page=2" })
                Check(!AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", unsafePage, out _), "Unsafe inbox page rejected: " + unsafePage);

            var sharedInbox = ApiContract.ParseNotificationPage(ReadFixture("notifications-page-1.json"));
            var sharedInboxLast = ApiContract.ParseNotificationPage(ReadFixture("notifications-page-2.json"));
            Check(sharedInbox.count == 21 && sharedInbox.results.Length == 20 && sharedInboxLast.results.Length == 1,
                "Shared inbox fixtures preserve both real notification pages");
            Check(sharedInbox.next.StartsWith("/api/notifications/", StringComparison.Ordinal)
                && AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", sharedInbox.next, out next)
                && next == "https://abby.example.com/api/notifications/?page=2",
                "Relative Django continuations retain the browser's HTTPS origin across HTTP proxy hops");
            for (int index = 0; index < sharedInbox.results.Length; index++)
                Check(sharedInbox.results[index].id == 101 + index && !sharedInbox.results[index].is_read,
                    "Reading a shared inbox page preserves each unread notification's identity");
            Check(sharedInboxLast.results[0].id == 121 && !sharedInboxLast.results[0].is_read && sharedInboxLast.next == null,
                "The final shared inbox page ends pagination without acknowledging updates");
            var sharedInboxEmpty = ApiContract.ParseNotificationPage(ReadFixture("notifications-empty.json"));
            Check(sharedInboxEmpty.count == 0 && sharedInboxEmpty.results.Length == 0 && sharedInboxEmpty.next == null,
                "An empty shared inbox preserves the real pagination envelope");

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

        private static void ValidateCompanionCareContracts()
        {
            string stableJson = ReadFixture("pets-stable.json");
            var stable = ApiContract.ParseStable(stableJson);
            Check(stable.total_pets == 3 && stable.total_mounts == 2 && stable.ActiveCompanion.id == 51 && stable.ActiveMount.id == 61,
                "Shared stable preserves authoritative creature counts and active IDs");
            Check(stable.ActiveCompanion.name == "Sprout {a} \"friend\"" && stable.ActiveCompanion.last_fed_at == null,
                "Shared companion preserves escaped names and absent feeding history");
            Check(ApiContract.ParseStable(ReadFixture("pets-stable-empty.json")).pets.Length == 0,
                "Shared empty collection never fabricates an owned creature");

            string inventoryJson = ReadFixture("inventory-food.json");
            var inventory = ApiContract.ParseInventoryPage(inventoryJson);
            Check(inventory.results.Length == 4 && inventory.count == 4 && inventory.next == null,
                "Shared bare inventory response preserves items without inventing pagination");
            int foods = 0;
            bool foundFavorite = false, foundNeutral = false, foundEgg = false;
            foreach (var entry in inventory.results)
            {
                if (entry.item.item_type == "food") foods++;
                if (entry.item.id == 71) foundFavorite = entry.quantity == 2 && entry.item.food_species_name == "Fox";
                if (entry.item.id == 72) foundNeutral = entry.quantity == 1 && entry.item.food_species_name == null;
                if (entry.item.id == 73) foundEgg = entry.item.item_type == "egg";
            }
            Check(foods == 3 && foundFavorite && foundNeutral && foundEgg,
                "Shared food and nonfood inventory preserve type, quantity and nullable preference");
            Check(ApiContract.ParseInventoryPage(ReadFixture("inventory-empty.json")).results.Length == 0,
                "Shared empty food inventory remains valid");
            var page = ApiContract.ParseInventoryPage("{\"count\":4,\"next\":null,\"results\":" + inventoryJson + "}");
            Check(page.results.Length == 4 && page.count == 4 && page.next == null, "Inventory accepts a bounded DRF page shape");
            string trimmedInventory = inventoryJson.Trim();
            string inventoryRecords = trimmedInventory.Substring(1, trimmedInventory.Length - 2);
            Reject(() => ApiContract.ParseInventoryPage("[" + inventoryRecords + "," + inventoryRecords + "]"), "Duplicate inventory rows cannot authorize extra feeds");
            Reject(() => ApiContract.ParseInventoryPage(inventoryJson.Replace("\"quantity\": 2", "\"quantity\": -1")), "Negative food quantities are rejected");
            Reject(() => ApiContract.ParseInventoryPage(inventoryJson.Replace("\"item_type\": \"food\"", "\"item_type\": null")), "Missing item types cannot become feed eligibility");
            Reject(() => ApiContract.ParseInventoryPage("{\"count\":10001,\"next\":null,\"results\":[]}"), "Inventory count is bounded");
            Reject(() => ApiContract.ParseInventoryPage("{\"count\":1,\"next\":\"?page=2\",\"results\":[]}"), "An empty inventory continuation is rejected");
            Check(AbbyApiClient.TryResolveInventoryPageUrl("https://abby.example.com", "/api/inventory/?page=2", out var next)
                && next == "https://abby.example.com/api/inventory/?page=2", "Food pages stay on the same-origin inventory endpoint");
            Check(AbbyApiClient.TryResolveInventoryPageUrl("https://abby.example.com", "/api/inventory/?page=2&_abby_session=0123456789abcdef0123456789abcdef", out next)
                && next == "https://abby.example.com/api/inventory/?page=2", "Food pagination strips the inherited private GET namespace");
            foreach (string unsafePage in new[] { "https://outside.example.com/api/inventory/?page=2", "http://abby.example.com/api/inventory/?page=2", "/api/auth/", "/api/inventory/?page=0", "/api/inventory/?page=501", "/api/inventory/?page=2&token=x", "/api/inventory/?page=2#secret", "https://user@abby.example.com/api/inventory/?page=2", "/api/inventory/?page=2&page=3", "/api/inventory/?page=2&_abby_session=bad" })
                Check(!AbbyApiClient.TryResolveInventoryPageUrl("https://abby.example.com", unsafePage, out _), "Unsafe food continuation rejected: " + unsafePage);

            string feedJson = ReadFixture("pet-feed.json");
            var feed = ApiContract.ParsePetFeed(feedJson, 20);
            Check(feed.growth_added == 15 && feed.new_growth == 35 && !feed.evolved && feed.mount_id == 0,
                "Shared confirmed feeding preserves growth without fabricating an evolved mount");
            var neutral = ApiContract.ParsePetFeed(ReadFixture("pet-feed-neutral.json"), 20);
            Check(neutral.growth_added == 5 && neutral.new_growth == 25, "Shared neutral feeding uses the server-confirmed outcome");
            string evolvedJson = ReadFixture("pet-feed-evolved.json");
            var evolved = ApiContract.ParsePetFeed(evolvedJson, 90);
            Check(evolved.growth_added == 15 && evolved.new_growth == 100 && evolved.evolved && evolved.mount_id == 83,
                "Shared evolution retains the clamped confirmed total and created mount ID");
            Reject(() => ApiContract.ParsePetFeed(feedJson.Replace("\"evolved\": false", "\"evolved\": \"false\"")), "Feeding confirmation requires an explicit evolution boolean");
            Reject(() => ApiContract.ParsePetFeed(feedJson.Replace("\"new_growth\": 35", "\"new_growth\": 101")), "Feeding cannot fabricate growth beyond evolution");
            Reject(() => ApiContract.ParsePetFeed(feedJson.Replace("\"mount_id\": null", "\"mount_id\": 83")), "Unevolved feeding cannot create a mount ID");
            Reject(() => ApiContract.ParsePetFeed(evolvedJson.Replace("\"mount_id\": 83", "\"mount_id\": null")), "Evolution must confirm the created mount");
            Reject(() => ApiContract.ParsePetFeed(evolvedJson.Replace("\"new_growth\": 100", "\"new_growth\": 99")), "Evolution requires the threshold total");
            Reject(() => ApiContract.ParsePetFeed(feedJson, 35), "An unchanged growth total cannot confirm feeding");

            OwnedPetDto expectedPet = null;
            OwnedMountDto expectedMount = null;
            foreach (var pet in stable.pets) if (pet.id == 52) expectedPet = pet;
            foreach (var mount in stable.mounts) if (mount.id == 62) expectedMount = mount;
            string activatedPetJson = ReadFixture("pet-activate.json");
            string activatedMountJson = ReadFixture("mount-activate.json");
            Check(ApiContract.ParsePetActivation(activatedPetJson, expectedPet).is_active,
                "Shared activation confirms the selected owned companion");
            Check(ApiContract.ParseMountActivation(activatedMountJson, expectedMount).is_active,
                "Shared activation confirms the selected owned mount");
            Reject(() => ApiContract.ParsePetActivation(activatedPetJson, stable.ActiveCompanion), "Another pet's response cannot confirm selection");
            Reject(() => ApiContract.ParseMountActivation(activatedMountJson, stable.ActiveMount), "Another mount's response cannot confirm selection");
            Reject(() => ApiContract.ParsePetActivation(activatedPetJson.Replace("\"is_active\": true", "\"is_active\": false"), expectedPet), "Inactive pet state cannot confirm selection");
            Reject(() => ApiContract.ParsePetActivation(activatedPetJson.Replace("\"evolved_to_mount\": false", "\"evolved_to_mount\": true"), expectedPet), "An evolved pet cannot become the active companion");
            Reject(() => ApiContract.ParseMountActivation(activatedMountJson.Replace("\"is_active\": true", "\"is_active\": false"), expectedMount), "Inactive mount state cannot confirm selection");
            const string expedition = "{\"id\":91,\"mount_id\":62,\"status\":\"active\",\"is_ready\":true,\"seconds_remaining\":-1}";
            string exploringMount = activatedMountJson.Replace("\"active_expedition\": null", "\"active_expedition\": " + expedition);
            Check(ApiContract.ParseOwnedMount(exploringMount).active_expedition.seconds_remaining == -1,
                "A returned but unclaimed expedition remains active and keeps Django's negative countdown");
            Reject(() => ApiContract.ParseMountActivation(exploringMount, expectedMount), "An exploring mount cannot confirm availability for selection");
            Reject(() => ApiContract.ParseOwnedMount(exploringMount.Replace("\"mount_id\":62", "\"mount_id\":61")), "An expedition must belong to its mount");
            foreach (string fixture in new[] { "pet-feed-missing-food.json", "pet-feed-unavailable-food.json", "pet-feed-already-evolved.json", "pet-not-owned.json", "mount-not-owned.json" })
                Check(!ApiContract.HttpError(400, ReadFixture(fixture), true, false).OutcomeUnknown, "Shared care rejection is definite: " + fixture);
        }

        private static void ValidateHatchingContracts()
        {
            string inventoryJson = ReadFixture("inventory-hatching.json");
            var inventory = ApiContract.ParseInventoryPage(inventoryJson);
            var egg = Array.Find(inventory.results, entry => entry.item.id == 73);
            var potion = Array.Find(inventory.results, entry => entry.item.id == 75);
            Check(egg != null && egg.id == 83 && egg.quantity == 2 && egg.item.item_type == "egg" && egg.item.pet_species_name == "Fox",
                "Hatching uses owned egg definition IDs, quantities and authoritative species names");
            Check(potion != null && potion.id == 85 && potion.quantity == 1 && potion.item.item_type == "potion" && potion.item.potion_type_name == "Ice",
                "Hatching uses owned potion definition IDs and authoritative potion names");
            string hatchJson = ReadFixture("pet-hatch.json");
            var previousIds = new HashSet<int>();
            foreach (var pet in ApiContract.ParseStable(ReadFixture("pets-stable.json")).pets) previousIds.Add(pet.id);
            var hatched = ApiContract.ParsePetHatch(hatchJson, egg.item, potion.item, previousIds);
            Check(hatched.id == 83 && hatched.species.id == 41 && hatched.potion.id == 44 && hatched.growth_points == 0
                && !hatched.is_active && !hatched.evolved_to_mount && !hatched.is_fully_grown && hatched.last_fed_at == null,
                "Shared hatch response confirms a new inactive, unfed companion with zero growth");
            Reject(() => ApiContract.ParsePetHatch(hatchJson, egg.item, potion.item, new HashSet<int> { 83 }),
                "An existing pet receipt cannot confirm another hatching");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"growth_points\": 0", "\"growth_points\": 5"), egg.item, potion.item, previousIds),
                "A grown creature cannot confirm a new hatch");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"is_active\": false", "\"is_active\": true"), egg.item, potion.item, previousIds),
                "Hatching cannot silently choose the active companion");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"evolved_to_mount\": false", "\"evolved_to_mount\": true"), egg.item, potion.item, previousIds),
                "An evolved creature cannot confirm a new hatch");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"last_fed_at\": null", "\"last_fed_at\": \"2026-10-10T12:00:00-07:00\""), egg.item, potion.item, previousIds),
                "A previously fed creature cannot confirm a new hatch");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"name\": \"Fox\"", "\"name\": \"Other species\""), egg.item, potion.item, previousIds),
                "The hatch receipt must match the typed egg species");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"name\": \"Ice\"", "\"name\": \"Other potion\""), egg.item, potion.item, previousIds),
                "The hatch receipt must match the typed potion");
            Reject(() => ApiContract.ParsePetHatch(hatchJson, potion.item, egg.item, previousIds),
                "Swapped ingredient types cannot confirm hatching");
            Reject(() => ApiContract.ParseInventoryPage(inventoryJson.Replace("\"pet_species_name\": \"Fox\"", "\"pet_species_name\": 41")),
                "Typed ingredient names cannot become inferred catalog IDs");
            Reject(() => ApiContract.ParseInventoryPage(inventoryJson.Replace("\"potion_type_name\": \"Ice\"", "\"potion_type_name\": true")),
                "Typed potion names must be nullable strings");
            Check(ApiContract.ParsePetHatch(hatchJson, new InventoryItemDto { item_type = "egg" }, new InventoryItemDto { item_type = "potion" }, previousIds).id == 83,
                "Legacy ingredients without typed display names retain the server-confirmed hatch outcome");
            foreach (string fixture in new[] { "pet-hatch-missing-ingredients.json", "pet-hatch-unavailable-egg.json", "pet-hatch-unavailable-potion.json", "pet-hatch-duplicate.json" })
                Check(!ApiContract.HttpError(400, ReadFixture(fixture), true, false).OutcomeUnknown,
                    "Shared hatch rejection is definite and never a successful reveal: " + fixture);
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
